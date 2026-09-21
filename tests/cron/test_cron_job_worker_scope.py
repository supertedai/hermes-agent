"""A cron job's processes must not inherit the triggering worker's Kanban scope.

A job can be fired *by hand* from inside a Kanban work session: ``hermes cron run`` from a
worker — or from a descendant of one, e.g. a shell inside a ``delegate_task`` child —
executes the script in the caller's own process, and delivers through a child spawned from
it too. Both build the child env from that process.

The lineage scrub already removes the worker's *identity* on those paths, but it deliberately
RETAINS location (:func:`agent.delegation_context.scrub_kanban_env`), so
``HERMES_KANBAN_WORKSPACE`` still points at ``…/kanban/workspaces/t_<hex>`` — whose basename
IS a card id — and ``TERMINAL_CWD`` names the same path again. A consumer that resolves a
task id from the environment (task variable first, workspace basename second) therefore files
its ledger line on the card that happened to trigger the run, while the SAME job on its
schedule files it on none. Measured on a real run: ``task_id=t_96702720`` by hand versus no
task id on the schedule.

The choice these tests bind, and why the other two were rejected:

* **not "refuse to run from a worker"** — refusing on ``HERMES_KANBAN_TASK`` would not even
  have caught the measured leak (identity is already stripped; the card id rides in the
  workspace path), and it deletes a legitimate workflow: hand-triggering a job from a work
  session is how a job is verified before its schedule does anything;
* **not a full env whitelist** — that drops PATH, HOME, the profile's own ``.env`` and its
  credentials, which the scheduled path has always provided, and would change jobs that
  legitimately want the environment.

So the job's processes lose the caller's *worker scope* (identity + workspace-scoped
location, plus the ``TERMINAL_CWD`` the dispatcher pins on the same workspace — the same path
under another name) and keep the board pointer (``HERMES_KANBAN_DB`` / ``_BOARD`` / ``_HOME``)
— a job has a legitimate board, never a legitimate caller. The write fence the caller's
children carry goes with the scope too: it is the caller's rule, not the job's, and a job
under it is a DIFFERENT job (``hermes kanban`` from its own script is denied when fired by
hand and allowed on the same job's scheduled run). The strip is gated on the
triggering PROCESS carrying the scope, so a board pointer a profile declared for itself is
never mistaken for an inherited one, and a scheduled run's environment is unchanged.
"""

from __future__ import annotations

import json
import subprocess
from unittest import mock

import pytest

WORKER_TASK = "t_96702720"
WORKER_WORKSPACE = f"/opt/hermes-tavle/kanban/workspaces/{WORKER_TASK}"


@pytest.fixture
def cron_home(tmp_path, monkeypatch):
    """A profile home with a ``scripts/`` dir, as ``_run_job_script`` requires."""
    home = tmp_path / ".hermes"
    (home / "scripts").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture
def worker_process(monkeypatch):
    """The shape the dispatcher spawns: identity, the workspace-scoped location, and the
    ``TERMINAL_CWD`` pin it installs on the same workspace."""
    for key, value in {
        "HERMES_KANBAN_TASK": WORKER_TASK,
        "HERMES_KANBAN_WORKSPACE": WORKER_WORKSPACE,
        "HERMES_KANBAN_WORKSPACES_ROOT": "/opt/hermes-tavle/kanban/workspaces",
        "HERMES_KANBAN_RUN_ID": "42",
        "HERMES_KANBAN_CLAIM_LOCK": "Hermes:986785",
        "HERMES_KANBAN_BRANCH": f"wt/{WORKER_TASK}",
        "HERMES_KANBAN_DB": "/opt/hermes-tavle/kanban.db",
        "HERMES_KANBAN_BOARD": "default",
        "HERMES_KANBAN_HOME": "/opt/hermes-tavle",
        "TERMINAL_CWD": WORKER_WORKSPACE,
    }.items():
        monkeypatch.setenv(key, value)
    return WORKER_TASK


def _job_env(cron_home, tmp_path, workdir=None) -> dict[str, str]:
    """Run a real job script through ``_run_job_script`` and return the env it received.

    The probe writes to a file instead of stdout so the assertions are made on the child's
    actual environment and not on the redacted copy that comes back from the run.
    """
    dump = tmp_path / "job-env.json"
    (cron_home / "scripts" / "envdump.py").write_text(
        "import json, os\n"
        f"json.dump(dict(os.environ), open({str(dump)!r}, 'w'))\n",
        encoding="utf-8",
    )
    from cron.scheduler_script import _run_job_script

    ok, output = _run_job_script("envdump.py", workdir=workdir)
    assert ok, output
    return json.loads(dump.read_text())


# ---------------------------------------------------------------------------
# The predicate and the filter
# ---------------------------------------------------------------------------

class TestWorkerScopePredicate:
    def test_identity_and_workspace_location_are_worker_scope(self):
        from agent.delegation_context import (
            KANBAN_ENV_KEYS, KANBAN_WORKER_SCOPE_KEYS, carries_kanban_worker_scope,
        )

        # The rule must not depend on the lineage scrub's side effect: identity is in here
        # explicitly, together with the location that carries the card id.
        assert set(KANBAN_ENV_KEYS) <= set(KANBAN_WORKER_SCOPE_KEYS)
        assert carries_kanban_worker_scope({"HERMES_KANBAN_TASK": WORKER_TASK}) is True
        assert carries_kanban_worker_scope(
            {"HERMES_KANBAN_WORKSPACE": WORKER_WORKSPACE}) is True

    def test_board_pointer_alone_is_not_worker_scope(self):
        """A profile may declare where its board is; that is not an inherited worker scope."""
        from agent.delegation_context import carries_kanban_worker_scope

        assert carries_kanban_worker_scope({
            "HERMES_KANBAN_DB": "/opt/hermes-tavle/kanban.db",
            "HERMES_KANBAN_BOARD": "default",
            "HERMES_KANBAN_HOME": "/opt/hermes-tavle",
        }) is False

    def test_strip_removes_scope_and_keeps_board_pointer_and_fence(self):
        from agent.delegation_context import (
            DELEGATED_CHILD_ENV_MARKER, strip_kanban_worker_scope,
        )

        cleaned = strip_kanban_worker_scope({
            "HERMES_KANBAN_TASK": WORKER_TASK,
            "HERMES_KANBAN_WORKSPACE": WORKER_WORKSPACE,
            DELEGATED_CHILD_ENV_MARKER: "/opt/hermes-tavle",
            "HERMES_KANBAN_DB": "/opt/hermes-tavle/kanban.db",
            "PATH": "/usr/bin",
        })
        assert "HERMES_KANBAN_TASK" not in cleaned
        assert "HERMES_KANBAN_WORKSPACE" not in cleaned
        assert cleaned["HERMES_KANBAN_DB"] == "/opt/hermes-tavle/kanban.db"
        assert cleaned[DELEGATED_CHILD_ENV_MARKER] == "/opt/hermes-tavle"
        assert cleaned["PATH"] == "/usr/bin"


# ---------------------------------------------------------------------------
# The job process, measured through the real spawn
# ---------------------------------------------------------------------------

class TestJobProcessScope:
    def test_worker_scope_does_not_reach_the_job(self, cron_home, tmp_path, worker_process):
        env = _job_env(cron_home, tmp_path)

        for key in ("HERMES_KANBAN_TASK", "HERMES_KANBAN_RUN_ID",
                    "HERMES_KANBAN_CLAIM_LOCK", "HERMES_KANBAN_BRANCH",
                    "HERMES_KANBAN_WORKSPACE", "HERMES_KANBAN_WORKSPACES_ROOT",
                    "TERMINAL_CWD"):
            assert key not in env, f"{key} reached the job process"

    def test_a_cwd_that_is_not_the_callers_workspace_survives(
            self, cron_home, tmp_path, worker_process, monkeypatch):
        """The strip matches the caller's workspace by VALUE: a cwd the profile declares for
        itself, or one the job's own workdir puts there, is not caller scope."""
        own = tmp_path / "somewhere-else"
        own.mkdir()
        monkeypatch.setenv("TERMINAL_CWD", str(own))

        env = _job_env(cron_home, tmp_path, workdir=str(own))

        assert env.get("TERMINAL_CWD") == str(own)
        assert not any(WORKER_TASK in str(v) for v in env.values())

    def test_no_value_handed_to_the_job_names_the_triggering_card(
            self, cron_home, tmp_path, worker_process):
        """The class-level bind: the measured failure was the card id riding in a *value*.

        Asserting on the key list alone would not have caught it — the leak came from a
        location variable that was deliberately retained. This holds for any future key.
        """
        env = _job_env(cron_home, tmp_path)

        leaked = {k: v for k, v in env.items() if WORKER_TASK in str(v)}
        assert leaked == {}, f"the job process can still name the caller's card: {leaked}"

    def test_the_descendant_shape_is_covered_too(self, cron_home, tmp_path, monkeypatch):
        """A shell inside a worker has the workspace and the fence, but no task variable."""
        from agent.delegation_context import DELEGATED_CHILD_ENV_MARKER

        monkeypatch.setenv("HERMES_KANBAN_WORKSPACE", WORKER_WORKSPACE)
        monkeypatch.setenv(DELEGATED_CHILD_ENV_MARKER, "/opt/hermes-tavle")

        env = _job_env(cron_home, tmp_path)

        assert "HERMES_KANBAN_WORKSPACE" not in env
        assert not any(WORKER_TASK in str(v) for v in env.values())

    def test_board_pointer_survives_so_a_job_keeps_reading_its_board(
            self, cron_home, tmp_path, worker_process):
        env = _job_env(cron_home, tmp_path)

        assert env.get("HERMES_KANBAN_DB") == "/opt/hermes-tavle/kanban.db"
        assert env.get("HERMES_KANBAN_BOARD") == "default"
        assert env.get("HERMES_KANBAN_HOME") == "/opt/hermes-tavle"

    def test_the_inherited_write_fence_does_not_reach_the_job(
            self, cron_home, tmp_path, worker_process):
        """The job's processes are not the caller's descendants, so the fence they would
        inherit is not their rule. Pinned because the opposite choice was defensible — the
        fence only ever denies, so keeping it looked like the safe direction — and the
        measurement that decides it is that ``hermes kanban`` from the job's own script is
        denied on a hand-fired run and allowed on the same job's scheduled run."""
        from agent.delegation_context import DELEGATED_CHILD_ENV_MARKER

        env = _job_env(cron_home, tmp_path)

        assert DELEGATED_CHILD_ENV_MARKER not in env

    def test_scheduled_run_environment_is_unchanged(self, cron_home, tmp_path, monkeypatch):
        """No worker scope in the triggering process -> the job env is exactly what the
        factory produced before, so scheduled runs cannot change behaviour."""
        from tools.environments.local import build_subprocess_env

        for key in ("HERMES_KANBAN_TASK", "HERMES_KANBAN_WORKSPACE",
                    "HERMES_KANBAN_WORKSPACES_ROOT", "HERMES_KANBAN_BRANCH",
                    "HERMES_DELEGATED_CHILD_CONTEXT", "TERMINAL_CWD"):
            monkeypatch.delenv(key, raising=False)

        assert _job_env(cron_home, tmp_path) == build_subprocess_env(
            strip_launch_profile=True)


# ---------------------------------------------------------------------------
# The delivery child, measured at the seam the lane actually uses
# ---------------------------------------------------------------------------

def test_delivery_child_is_not_handed_the_callers_card(worker_process):
    """``--deliver`` spawns a child too; it belongs to the job, not to the card that
    triggered the run."""
    from cron import scheduler_delivery as sched_delivery
    from agent.delegation_context import DELEGATED_CHILD_ENV_MARKER

    calls: dict = {}

    def fake_run(argv, env, report_path, timeout):
        calls["env"] = env
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with mock.patch.object(sched_delivery, "_run_bot_chat_turn", side_effect=fake_run), \
         mock.patch.object(sched_delivery.shutil, "which", return_value="/usr/bin/hermes"):
        err = sched_delivery._deliver_to_bot_chat(
            {"id": "j1", "name": "Daily digest"}, "the output", "")

    assert err is None, err
    env = calls["env"]
    for key in ("HERMES_KANBAN_TASK", "HERMES_KANBAN_WORKSPACE", "TERMINAL_CWD"):
        assert key not in env, f"{key} reached the delivery child"
    assert DELEGATED_CHILD_ENV_MARKER not in env
    assert not any(WORKER_TASK in str(v) for v in env.values())
