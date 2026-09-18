"""Safety tests for the cron-facing Kanban enqueue boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_cli import kanban as kc
from hermes_cli import kanban_db as kb


def _json_line(out: str) -> str:
    """Hent JSON-linja ut av run_slash-svaret.

    ``run_slash`` slår sammen stdout og stderr, og en advarsel på stderr
    (f.eks. «ingen --assignee») skal ikke gjøre et gyldig JSON-svar
    uparsbart.
    """
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("{"):
            return stripped
    raise AssertionError(f"ingen JSON-linje i svaret: {out!r}")


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def test_enqueue_is_idempotent_and_updates_existing_card(kanban_home):
    first = json.loads(
        kc.run_slash(
            "enqueue 'EFC maintenance' --body old --assignee worker "
            "--workspace worktree:/repo --branch wt/efc-maintenance "
            "--idempotency-key cron:436e52f74907 --json"
        )
    )
    second = json.loads(
        kc.run_slash(
            "enqueue 'EFC maintenance refreshed' --body new --assignee worker "
            "--priority 7 --idempotency-key cron:436e52f74907 --json"
        )
    )

    assert first["created"] is True
    assert second == {
        "task_id": first["task_id"],
        "created": False,
        "status": "ready",
    }
    with kb.connect_closing() as conn:
        task = kb.get_task(conn, first["task_id"])
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE idempotency_key = ?",
            ("cron:436e52f74907",),
        ).fetchone()["n"]
    assert count == 1
    assert task.title == "EFC maintenance refreshed"
    assert task.body == "new"
    assert task.priority == 7
    assert task.workspace_kind == "worktree"
    assert task.workspace_path == "/repo"
    assert task.branch_name == "wt/efc-maintenance"


def test_enqueue_requeues_terminal_card_without_touching_running_claim(kanban_home):
    first = json.loads(
        _json_line(kc.run_slash("enqueue run --idempotency-key cron:test --json"))
    )
    with kb.connect_closing() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = 123 WHERE id = ?",
            (first["task_id"],),
        )
        conn.commit()
    refreshed = json.loads(_json_line(kc.run_slash("enqueue rerun --idempotency-key cron:test --json")))
    assert refreshed["task_id"] == first["task_id"]
    assert refreshed["status"] == "ready"

    running = json.loads(_json_line(kc.run_slash("enqueue active --idempotency-key cron:active --json")))
    with kb.connect_closing() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running', claim_lock = 'host:1', "
            "worker_pid = 42 WHERE id = ?",
            (running["task_id"],),
        )
        conn.commit()
    kc.run_slash("enqueue active-refresh --idempotency-key cron:active")
    with kb.connect_closing() as conn:
        row = conn.execute(
            "SELECT status, claim_lock, worker_pid FROM tasks WHERE id = ?",
            (running["task_id"],),
        ).fetchone()
    assert tuple(row) == ("running", "host:1", 42)


def test_enqueue_omitted_flags_do_not_clobber_existing_fields(kanban_home):
    """En producer som ikke gjentar et flagg skal ikke AVVÆPNE kortet.

    Målt 2026-09-18: `--priority` hadde default 0 og `--assignee`/`--body`
    default None, så en senere enqueue uten flaggene nullet prioritet, fjernet
    eieren og tømte bodyen. Et kort uten assignee sendes aldri ut av
    dispatcheren — altså en stille avvæpning av vedlikeholdskortet.
    """
    first = json.loads(
        kc.run_slash(
            "enqueue 'EFC maintenance' --body keep-me --assignee researcher "
            "--priority 7 --idempotency-key cron:efc --json"
        )
    )
    kc.run_slash("enqueue 'EFC maintenance refreshed' --idempotency-key cron:efc")
    with kb.connect_closing() as conn:
        task = kb.get_task(conn, first["task_id"])
    assert task is not None
    assert task.title == "EFC maintenance refreshed"
    assert task.assignee == "researcher"
    assert task.body == "keep-me"
    assert task.priority == 7


def test_enqueue_without_assignee_warns_that_nobody_will_run_it(kanban_home):
    """Et kort uten eier kan aldri sendes ut — fraværet skal være synlig."""
    out = kc.run_slash("enqueue 'eierlos' --idempotency-key cron:eierlos --json")
    payload = json.loads(_json_line(out))
    assert payload["created"] is True
    assert "assignee" in out.lower()
    assert "sendes" in out.lower() or "dispatch" in out.lower()


def test_dispatcher_claims_worktree_task_and_injects_task_environment(
    kanban_home, monkeypatch
):
    captured = {}

    class FakeProc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return FakeProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    with kb.connect_closing() as conn:
        task_id = kb.create_task(
            conn,
            title="worktree maintenance",
            assignee="worker",
            workspace_kind="worktree",
            workspace_path="/repo",
            branch_name="wt/maintenance",
        )
        claimed = kb.claim_task(conn, task_id, claimer="dispatcher")
        assert claimed is not None
        task = kb.get_task(conn, task_id)
        workspace = "/repo/.worktrees/" + task_id
        pid = kb._default_spawn(task, workspace)

    assert pid == 4242
    assert captured["env"]["HERMES_KANBAN_TASK"] == task_id
    assert captured["env"]["HERMES_KANBAN_BOARD"] == "default"
    assert "worker" in captured["cmd"]
