"""A run the kernel declared wedged must not keep holding a shared lock (#115692).

The measured production defect: a cron external worker deadlocked in ``futex_do_wait`` passed
``_owner_is_live()`` forever, so ``recover_interrupted_executions`` had no proof to act on. The row
was eventually released as ``unknown`` by the derived stale bound — but the *process* was left
running, and it kept holding ``/opt/opus-ledger/lmstudio-semafoer.laas`` from 06:30Z onward. Every
other consumer of that lock (six cron jobs, ``dyptenker``, ``schema-hoster``, and the watchdog meant
to measure the starvation) then burned its deferral ladder while nothing measured it.

These tests use a REAL child process holding a REAL ``flock``, because the property under test is
"the kernel releases the lock when the owner dies" — a mock cannot show that. The sweep is the only
observer that sees both ends (the ledger row and the foreign pid), which is why the termination
lives there.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import textwrap
import uuid
from datetime import timedelta

import pytest

import cron.executions as executions_mod
from cron.executions import (
    _hermes_now,
    _process_start_time,
    _transaction,
    recover_interrupted_executions,
)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Isolated HERMES_HOME so jobs.json and executions.db are both temp-local."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_CRON_TIMEOUT", "600")
    yield tmp_path


def _spawn_lock_holder(lock_path, *, ignore_sigterm: bool = False) -> subprocess.Popen:
    """Child that takes an exclusive ``flock`` and sleeps — a stand-in for a wedged worker.

    Prints ``ready`` only AFTER the lock is held, so the test never races the acquisition.
    """
    code = textwrap.dedent(
        """
        import fcntl, os, signal, sys, time
        if sys.argv[2] == "ignore-sigterm":
            signal.signal(signal.SIGTERM, lambda *a: None)
        fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        print("ready", flush=True)
        time.sleep(300)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(lock_path),
         "ignore-sigterm" if ignore_sigterm else "plain"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    return proc


def _lock_is_free(lock_path) -> bool:
    """Try the lock itself; a live holder in another process makes LOCK_NB fail."""
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _seed_row(job_id: str, pid: int, *, age_seconds: float, started_at=None) -> str:
    claimed_at = (_hermes_now() - timedelta(seconds=age_seconds)).isoformat()
    with _transaction() as conn:
        eid = uuid.uuid4().hex
        conn.execute(
            """INSERT INTO executions
               (id, job_id, status, source, process_id, pid, process_started_at, claimed_at)
               VALUES (?, ?, 'running', 'cron', 'ext-proc', ?, ?, ?)""",
            (eid, job_id, pid, _process_start_time(pid) if started_at is None else started_at,
             claimed_at),
        )
    return eid


def _row(eid: str) -> dict:
    with _transaction() as conn:
        return dict(conn.execute("SELECT * FROM executions WHERE id=?", (eid,)).fetchone())


def _wait_gone(proc: subprocess.Popen, timeout: float = 10.0) -> None:
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:  # pragma: no cover - only on a fix regression
        proc.kill()
        pytest.fail("wedged owner was not terminated")


def _stale_age() -> float:
    """Age past the derived bound, read from the module instead of restating the formula."""
    bound = executions_mod._live_owner_stale_after_seconds()
    assert bound is not None
    return bound + 60


def test_a_wedged_owner_is_terminated_and_its_flock_is_released(ledger, tmp_path, monkeypatch):
    """THE regression: a wedged owner dies, so the shared ``flock`` it held is released.

    Both halves of the SIGTERM→SIGKILL contract are exercised: a cooperative child ends on SIGTERM,
    and a child that ignores SIGTERM is escalated instead of being leaked (the grace window is
    shortened so the test does not sleep through the production 10 s).
    """
    lock_path = tmp_path / "shared.laas"
    holder = _spawn_lock_holder(lock_path)
    try:
        assert not _lock_is_free(lock_path), "precondition: the child holds the shared lock"
        eid = _seed_row("job-wedged", holder.pid, age_seconds=_stale_age())

        assert recover_interrupted_executions() == 1

        _wait_gone(holder)
        assert _lock_is_free(lock_path), (
            "the wedged owner was released in the ledger but still holds the shared lock"
        )
        row = _row(eid)
        assert row["status"] == "unknown"
        assert "terminated" in row["error"] and "#115692" in row["error"]
        assert "shared locks held by this process are released" in row["error"]
    finally:
        if holder.poll() is None:  # pragma: no cover - only on a fix regression
            holder.kill()
        holder.wait()

    monkeypatch.setattr(executions_mod, "WEDGED_TERM_GRACE_SECONDS", 0.5)
    stubborn_path = tmp_path / "stubborn.laas"
    stubborn = _spawn_lock_holder(stubborn_path, ignore_sigterm=True)
    try:
        assert not _lock_is_free(stubborn_path)
        eid2 = _seed_row("job-sigterm-ignorer", stubborn.pid, age_seconds=_stale_age())

        assert recover_interrupted_executions() == 1

        _wait_gone(stubborn, timeout=executions_mod.WEDGED_KILL_GRACE_SECONDS + 10)
        assert stubborn.returncode == -signal.SIGKILL
        assert _lock_is_free(stubborn_path)
        assert "terminated" in _row(eid2)["error"]
    finally:
        if stubborn.poll() is None:  # pragma: no cover
            stubborn.kill()
        stubborn.wait()


def test_no_owner_is_signalled_without_a_bound_and_proof_of_ownership(
    ledger, tmp_path, monkeypatch
):
    """The two guards on the kill: the derived bound, and the start-time fingerprint.

    A recently claimed run is a legitimately running job, not a wedge. And a row whose recorded pid
    now belongs to a *different* process (the kernel recycled the number) may never be signalled —
    a leaked lock is the lesser harm, and the ledger has to say so.
    """
    lock_path = tmp_path / "shared.laas"
    holder = _spawn_lock_holder(lock_path)
    try:
        recent = _seed_row("job-live", holder.pid, age_seconds=60)
        assert recover_interrupted_executions() == 0
        assert holder.poll() is None, "a legitimately running job was terminated"
        assert _row(recent)["status"] == "running"

        recycled = _seed_row(
            "job-recycled", holder.pid, age_seconds=_stale_age(),
            started_at=(_process_start_time(holder.pid) or 0) - 5,
        )
        # Liveness alone must not be enough to authorise a signal.
        monkeypatch.setattr(executions_mod, "_owner_is_live", lambda pid, started_at: True)

        assert recover_interrupted_executions() == 1

        assert holder.poll() is None, "a recycled pid was killed"
        row = _row(recycled)
        assert row["status"] == "unknown"
        assert "was NOT signalled" in row["error"]
    finally:
        if holder.poll() is None:
            holder.kill()
        holder.wait()


def test_the_job_can_fire_again_after_its_wedged_owner_is_terminated(ledger, tmp_path):
    """"Fire claim lost" is the symptom; a claimable job is the cure.

    The wedged worker is the process that keeps the job's fire claim fresh. Once it is dead the
    claim can no longer be refreshed, so the next fire wins the claim instead of losing to a corpse.
    The claim is simulated at the TTL boundary because that is the only state a live refresher
    cannot produce — and the point of the fix is that no live refresher remains.
    """
    from cron.jobs import FIRE_CLAIM_TTL_SECONDS, claim_job_for_fire, create_job, get_job, update_job

    job_id = create_job(prompt="x", schedule="every 120m", name="wedged-fire")["id"]
    lock_path = tmp_path / "shared.laas"
    holder = _spawn_lock_holder(lock_path)
    try:
        eid = _seed_row(job_id, holder.pid, age_seconds=_stale_age())

        assert recover_interrupted_executions() == 1
        _wait_gone(holder)
        assert _lock_is_free(lock_path)

        # The owner that could refresh the claim is gone: after the TTL nothing can renew it.
        stale_at = (_hermes_now() - timedelta(seconds=FIRE_CLAIM_TTL_SECONDS + 30)).isoformat()
        update_job(job_id, {"fire_claim": {"at": stale_at, "by": "Hermes:999:dead"}})

        assert claim_job_for_fire(job_id) is True, "the job could not fire again after the wedge"
        claimed = get_job(job_id)
        assert claimed is not None
        assert (claimed.get("fire_claim") or {}).get("by") != "Hermes:999:dead"
        assert _row(eid)["status"] == "unknown"
    finally:
        if holder.poll() is None:
            holder.kill()
        holder.wait()
