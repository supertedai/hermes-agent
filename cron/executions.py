"""Profile-local durable audit ledger for cron execution attempts.

The ledger records what is known about each attempt; it is not a retry queue. Interrupted attempts
become ``unknown`` only once the attempt can no longer reach a terminal state: its exact owner is
proved gone, or the owner is alive but provably no longer working on it (a claim that outlived the
derived stale bound is treated as wedged and the owner is terminated, see
``recover_interrupted_executions``). Terminal states are immutable.
"""

from __future__ import annotations

import logging
import math
import os
import signal
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from hermes_constants import get_hermes_home
from hermes_time import now as _hermes_now
from cron.constants import CLAIM_TTL_INACTIVITY_HEADROOM

# Optional test override. Production resolves the path at transaction time so dashboard operations
# that temporarily enter another profile cannot leak that profile's records into the import-time
# home.
EXECUTIONS_FILE: Optional[Path] = None
MAX_TERMINAL_EXECUTIONS = 1000
HANDOFF_ADOPTION_GRACE_SECONDS = 30.0
# Floor for the live-owner stale-claim bound (#115692); see _live_owner_stale_after_seconds.
LIVE_OWNER_STALE_CLAIM_FLOOR_SECONDS = 7200.0
_TERMINAL_STATES = ("completed", "failed", "unknown")
_lock = threading.RLock()
_PROCESS_ID = uuid.uuid4().hex
logger = logging.getLogger(__name__)

#: Grace between SIGTERM and the escalated SIGKILL when a wedged owner is terminated. The sweep
#: runs in the gateway tick, so the wait is bounded and only paid when a wedge is actually proven.
WEDGED_TERM_GRACE_SECONDS = 10.0
WEDGED_KILL_GRACE_SECONDS = 5.0
_WEDGED_POLL_SECONDS = 0.05


# --- executions ledger --------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    # Late imports: a scheduler daemon that outlives an on-disk upgrade already has the OLD
    # ``hermes_cli.sqlite_util`` / ``cron.jobs`` cached, so new names must be resolved at call time,
    # not at import time (the guarantee cron/ledger.py used to carry, see e24c8499).
    from cron.jobs import _ensure_cron_dir
    from hermes_cli.sqlite_util import open_db

    path = EXECUTIONS_FILE or (get_hermes_home().resolve() / "cron" / "executions.db")
    _ensure_cron_dir(path.parent)
    return open_db(path, db_label="cron/executions.db", synchronous_full=True, initialize=_initialize_schema)


def _initialize_schema(conn: sqlite3.Connection) -> None:
    from hermes_cli.sqlite_util import add_column_if_missing

    conn.execute(
        """CREATE TABLE IF NOT EXISTS executions (
             id TEXT PRIMARY KEY,
             job_id TEXT NOT NULL,
             source TEXT NOT NULL,
             process_id TEXT NOT NULL,
             pid INTEGER NOT NULL,
             process_started_at INTEGER,
             status TEXT NOT NULL CHECK(status IN
               ('claimed','running','completed','failed','unknown')),
             handoff_pending INTEGER NOT NULL DEFAULT 0,
             handoff_started_at REAL,
             claimed_at TEXT NOT NULL,
             started_at TEXT,
             finished_at TEXT,
             error TEXT
           )"""
    )
    add_column_if_missing(
        conn, "executions", "handoff_pending",
        "handoff_pending INTEGER NOT NULL DEFAULT 0",
    )
    add_column_if_missing(
        conn, "executions", "handoff_started_at", "handoff_started_at REAL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_job_claimed "
        "ON executions(job_id, claimed_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_status_claimed "
        "ON executions(status, claimed_at DESC, id DESC)"
    )
    add_column_if_missing(conn, "executions", "delivery_outcome", "delivery_outcome TEXT")
    add_column_if_missing(conn, "executions", "scheduled_instant", "scheduled_instant TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_occurrence "
        "ON executions(job_id, scheduled_instant) WHERE status='completed'"
    )


@contextmanager
def _transaction() -> Iterator[sqlite3.Connection]:
    from hermes_cli.sqlite_util import transaction

    with _lock, transaction(_connect()) as conn:
        yield conn


def _fetch(conn: sqlite3.Connection, execution_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM executions WHERE id=?", (execution_id,)).fetchone()
    return dict(row) if row is not None else None


def _emit_execution_state(
    record: Optional[Dict[str, Any]], *, delivery_outcome: Optional[str] = None
) -> None:
    """Project durable state to monitoring without affecting ledger behavior."""
    try:
        from agent.monitoring.cron_health import emit_execution_state

        emit_execution_state(record, delivery_outcome=delivery_outcome)
    except Exception:
        pass


def _process_start_time(pid: int) -> Optional[int]:
    try:
        from gateway.status import get_process_start_time
        return get_process_start_time(pid)
    except Exception:
        return None


def _owner_is_live(pid: int, started_at: Optional[int]) -> bool:
    try:
        from gateway.status import _pid_exists
        if not _pid_exists(pid):
            return False
    except Exception:
        return True  # fail safe: inability to prove death must not rewrite state
    if started_at is None:
        return pid == os.getpid()
    current = _process_start_time(pid)
    return current is not None and current == started_at


def _live_owner_stale_after_seconds() -> Optional[float]:
    """Age past which a claimed/running row with a LIVE owner is treated as wedged.

    Derived from the existing knobs, never a bare wall-clock constant:
    ``max(3 × HERMES_CRON_TIMEOUT, cron script timeout, 7200)``. Returns ``None`` (never reclaim
    live owners — today's behaviour) when the inactivity timeout is 0/unlimited or not a finite
    positive number: with no bound to derive from, fail closed.
    """
    from cron.scheduler import _cron_inactivity_seconds
    from cron.scheduler_script import _get_script_timeout

    inactivity = float(_cron_inactivity_seconds())
    if not math.isfinite(inactivity) or inactivity <= 0:
        return None
    return max(
        inactivity * CLAIM_TTL_INACTIVITY_HEADROOM,
        float(_get_script_timeout()),
        LIVE_OWNER_STALE_CLAIM_FLOOR_SECONDS,
    )


def _claim_age_seconds(claimed_at: str) -> float:
    """Seconds since ``claimed_at`` (NOT NULL, always the aware ISO string from hermes_time.now)."""
    return (_hermes_now() - datetime.fromisoformat(claimed_at)).total_seconds()


def _handoff_in_grace(row: Dict[str, Any]) -> bool:
    """True while a freshly handed-off claim may still be adopted by its external worker."""
    handoff_started_at = row["handoff_started_at"]
    return bool(
        row["handoff_pending"]
        and handoff_started_at is not None
        and time.time() - float(handoff_started_at) < HANDOFF_ADOPTION_GRACE_SECONDS
    )


def _owner_identity_proven(pid: int, started_at: Optional[int]) -> bool:
    """True only when the process behind ``pid`` is provably the one that owns the claim.

    Deliberately independent of ``_owner_is_live``: that predicate answers "is the owner still
    alive" (and is stubbed by tests), while this one answers "is the number still the owner" —
    the only question that may be answered before signalling a foreign process. A recycled pid,
    a zombie, an unreadable ``/proc`` or a missing fingerprint all answer *no*, and the caller
    then leaves the process alone: a leaked claim beats killing a stranger.
    """
    if started_at is None or pid <= 1 or pid == os.getpid():
        return False
    current = _process_start_time(pid)
    if current is None:
        return False
    # ``getattr``, not ``from ... import``: older checkouts of gateway/status.py predate the
    # drift-tolerant matcher, and this module must import cleanly against both.
    try:
        import gateway.status as gateway_status
        matcher = getattr(gateway_status, "start_time_fingerprints_match", None)
    except Exception:
        matcher = None
    if matcher is None:
        return current == int(started_at)
    try:
        return bool(matcher(int(started_at), current))
    except Exception:
        return current == int(started_at)


def _owner_still_owns(pid: int, started_at: Optional[int]) -> bool:
    """Liveness AND identity in one probe, re-asked before every signal and every poll."""
    return _owner_identity_proven(pid, started_at) and _owner_is_live(pid, started_at)


def _pid_alive(pid: int) -> bool:
    try:
        from gateway.status import _pid_exists
        return bool(_pid_exists(pid))
    except Exception:
        return True  # cannot prove death -> do not claim it


def _signal_quietly(pid: int, sig: int) -> bool:
    """Send one signal to a proven owner; never raise, never report a lost race as success."""
    try:
        os.kill(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except (OSError, PermissionError) as exc:
        logger.warning("Could not signal wedged cron owner pid %d with %s: %s", pid, sig, exc)
        return False


def _wait_for_owner_exit(pid: int, started_at: Optional[int], deadline: float) -> bool:
    while time.monotonic() < deadline:
        if not _owner_still_owns(pid, started_at):
            return True
        time.sleep(_WEDGED_POLL_SECONDS)
    return not _owner_still_owns(pid, started_at)


def terminate_wedged_owner(
    pid: int, started_at: Optional[int], *, term_grace: Optional[float] = None,
    kill_grace: Optional[float] = None,
) -> str:
    """Terminate the proven owner of a wedged claim: SIGTERM, bounded wait, then SIGKILL.

    A process the kernel has already declared wedged must not keep holding a shared lock: a
    ``flock`` outliving the run it belongs to stops every other consumer of that lock — including
    the watchdog meant to measure the starvation (#115692). Killing the owner is what actually
    releases the lock, because the lock lives in the owner's open file description.

    Returns ``"gone"`` (nothing to terminate), ``"terminated"`` (SIGTERM was enough), ``"killed"``
    (SIGKILL was needed), ``"survived"`` (still provably alive after both windows — e.g. stuck in
    uninterruptible I/O) or ``"unproven"`` (identity could not be proved; nothing was signalled).
    """
    if not _owner_identity_proven(pid, started_at):
        return "gone" if not _pid_alive(pid) else "unproven"
    if not _signal_quietly(pid, signal.SIGTERM):
        return "gone"
    grace = WEDGED_TERM_GRACE_SECONDS if term_grace is None else float(term_grace)
    if _wait_for_owner_exit(pid, started_at, time.monotonic() + max(0.0, grace)):
        return "terminated"
    kill = getattr(signal, "SIGKILL", None)
    if kill is None:  # pragma: no cover - Windows has no SIGKILL
        return "survived"
    if not _signal_quietly(pid, kill):
        return "gone"
    kill_window = WEDGED_KILL_GRACE_SECONDS if kill_grace is None else float(kill_grace)
    if _wait_for_owner_exit(pid, started_at, time.monotonic() + max(0.0, kill_window)):
        return "killed"
    return "survived"


def _prune_unlocked(conn: sqlite3.Connection) -> None:
    conn.execute(
        """DELETE FROM executions WHERE id IN (
             SELECT id FROM executions
             WHERE status IN ('completed','failed','unknown')
             ORDER BY finished_at DESC, claimed_at DESC, id DESC LIMIT -1 OFFSET ?
           )""",
        (max(0, int(MAX_TERMINAL_EXECUTIONS)),),
    )


def create_execution(
    job_id: str, *, source: str, scheduled_instant: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a claimed attempt before executor/provider dispatch."""
    from cron.occurrences import scheduled_instant as canonical_instant

    now = _hermes_now().isoformat()
    execution_id = uuid.uuid4().hex
    pid = os.getpid()
    with _transaction() as conn:
        conn.execute(
            """INSERT INTO executions
               (id, job_id, source, process_id, pid, process_started_at,
                status, claimed_at, scheduled_instant)
               VALUES (?, ?, ?, ?, ?, ?, 'claimed', ?, ?)""",
            (execution_id, str(job_id), str(source), _PROCESS_ID, pid,
             _process_start_time(pid), now, canonical_instant(scheduled_instant)),
        )
        record = _fetch(conn, execution_id)
    _emit_execution_state(record)
    return record  # type: ignore[return-value]


def set_execution_occurrence(execution_id: str, instant: Optional[str]) -> None:
    """Bind the store-claimed snapshot before a provider hands it to a worker."""
    from cron.occurrences import scheduled_instant

    with _transaction() as conn:
        cur = conn.execute(
            "UPDATE executions SET scheduled_instant=? WHERE id=? AND status='claimed' "
            "AND handoff_pending=0 AND process_id=? AND pid=?",
            (scheduled_instant(instant), execution_id, _PROCESS_ID, os.getpid()),
        )
        if cur.rowcount != 1:
            raise RuntimeError("Cron occurrence could not be bound before dispatch")


def mark_execution_handoff_pending(execution_id: str) -> Optional[Dict[str, Any]]:
    """Fence restart recovery while an external worker is adopting a claim."""
    with _transaction() as conn:
        cur = conn.execute(
            """UPDATE executions
               SET handoff_pending=1, handoff_started_at=?
               WHERE id=? AND status='claimed'
                 AND process_id=? AND pid=?""",
            (time.time(), execution_id, _PROCESS_ID, os.getpid()),
        )
        if cur.rowcount != 1:
            return None
        record = _fetch(conn, execution_id)
    _emit_execution_state(record)
    return record


def adopt_claimed_execution(execution_id: str) -> Optional[Dict[str, Any]]:
    """Atomically transfer and start an attempt in its worker process.

    The dispatching gateway creates the row before spawning a restart-safe
    worker.  Adoption is the single ``claimed`` → ``running`` gate: only the
    winner may acknowledge ownership or run side effects.
    """
    pid = os.getpid()
    process_started_at = _process_start_time(pid)
    now = _hermes_now().isoformat()
    with _transaction() as conn:
        cur = conn.execute(
            """UPDATE executions
               SET process_id=?, pid=?, process_started_at=?,
                   status='running', started_at=?, handoff_pending=0,
                   handoff_started_at=NULL
               WHERE id=? AND status='claimed' AND handoff_pending=1""",
            (_PROCESS_ID, pid, process_started_at, now, execution_id),
        )
        if cur.rowcount != 1:
            return None
        record = _fetch(conn, execution_id)
    _emit_execution_state(record)
    return record


def mark_execution_running(execution_id: str) -> Optional[Dict[str, Any]]:
    """Transition one claimed attempt to running exactly once."""
    now = _hermes_now().isoformat()
    with _transaction() as conn:
        cur = conn.execute(
            """UPDATE executions
               SET status='running', started_at=?, handoff_pending=0,
                   handoff_started_at=NULL
               WHERE id=? AND status='claimed' AND handoff_pending=0
                 AND process_id=? AND pid=?""",
            (now, execution_id, _PROCESS_ID, os.getpid()),
        )
        if cur.rowcount != 1:
            return None
        record = _fetch(conn, execution_id)
    _emit_execution_state(record)
    return record


def finish_execution(
    execution_id: str, *, success: bool, error: Optional[str] = None,
    delivery_outcome: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Write a terminal result once; terminal attempts cannot be rewritten."""
    now = _hermes_now().isoformat()
    status = "completed" if success else "failed"
    detail = None if success else (str(error) if error else "unknown failure")
    with _transaction() as conn:
        cur = conn.execute(
            """UPDATE executions
               SET status=?, finished_at=?, error=?, handoff_pending=0,
                   handoff_started_at=NULL, delivery_outcome=?
               WHERE id=? AND status IN ('claimed','running')
                 AND process_id=? AND pid=?""",
            (status, now, detail, delivery_outcome, execution_id, _PROCESS_ID, os.getpid()),
        )
        if cur.rowcount != 1:
            return None
        _prune_unlocked(conn)
        record = _fetch(conn, execution_id)
    _emit_execution_state(record, delivery_outcome=delivery_outcome)
    return record


_OWNER_GONE_REASON = (
    "Scheduler restarted after this execution's owner exited before a durable "
    "terminal state; whether side effects ran is unknown."
)
_OWNER_WEDGED_REASON = (
    "Owner process was still alive but the claim outlived the derived stale bound; treated as "
    "wedged (#115692). Whether the process still holds its shared locks, and whether side "
    "effects ran, is unknown."
)
_OWNER_WEDGED_TERMINATED_REASON = (
    "Owner process was still alive but the claim outlived the derived stale bound; "
    "treated as wedged (#115692) and terminated (SIGTERM, then SIGKILL if it ignored the "
    "grace window) so the shared locks it held are released. Whether side effects ran "
    "before the termination is unknown."
)
_OWNER_WEDGED_GONE_REASON = (
    "Owner process was still alive when the claim outlived the derived stale bound, but "
    "exited while the sweep ran; treated as wedged (#115692). Its shared locks are released "
    "with it; whether side effects ran is unknown."
)
_OWNER_WEDGED_SURVIVED_REASON = (
    "Owner process is still alive after the claim outlived the derived stale bound; treated "
    "as wedged (#115692). Termination was attempted (SIGTERM, then SIGKILL) but the process "
    "could not be proved gone, so the shared locks it holds may still be held and whether "
    "side effects ran is unknown."
)
_OWNER_WEDGED_UNPROVEN_REASON = (
    "Owner process is still alive after the claim outlived the derived stale bound; treated "
    "as wedged (#115692). The recorded pid no longer matches the claim's owner (start-time "
    "mismatch), so it was NOT signalled — a recycled pid is never killed. Whether side effects "
    "ran is unknown."
)


#: One row per termination outcome: the ledger reason it earns, the log level it deserves, and the
#: phrase the log line uses. A table, not a ladder — the outcome space is closed by
#: ``terminate_wedged_owner``'s contract.
_WEDGED_OUTCOMES: Dict[str, tuple] = {
    "terminated": (
        _OWNER_WEDGED_TERMINATED_REASON, logging.WARNING, "terminated after SIGTERM",
    ),
    "killed": (
        _OWNER_WEDGED_TERMINATED_REASON, logging.WARNING, "terminated after SIGTERM→SIGKILL",
    ),
    "gone": (
        _OWNER_WEDGED_GONE_REASON, logging.WARNING, "exited while the sweep ran",
    ),
    "survived": (
        _OWNER_WEDGED_SURVIVED_REASON, logging.ERROR,
        "survived SIGTERM→SIGKILL; its shared locks may still be held",
    ),
    "unproven": (
        _OWNER_WEDGED_UNPROVEN_REASON, logging.ERROR,
        "pid could not be proved to be the claim's owner (start-time mismatch); not signalled",
    ),
}


def _wedged_reason(outcome: str) -> str:
    """Name what actually happened to the wedged owner; never claim a lock release unproven."""
    return _WEDGED_OUTCOMES.get(outcome, (_OWNER_WEDGED_REASON,))[0]


def _log_wedged_outcome(row: Dict[str, Any], outcome: str) -> None:
    """One log line per wedged row, at a level that matches whether locks were released."""
    _reason, level, note = _WEDGED_OUTCOMES.get(
        outcome, (_OWNER_WEDGED_REASON, logging.DEBUG, "outcome not described")
    )
    logger.log(
        level, "Wedged cron execution %s (job %s, pid %s): %s (#115692)",
        row["id"], row.get("job_id", "?"), row["pid"], note,
    )


def _recover_row(conn: sqlite3.Connection, row: Dict[str, Any], reason: str, now: str) -> bool:
    """CAS one claimed/running row to ``unknown``; True only for the writer that won."""
    cur = conn.execute(
        """UPDATE executions
           SET status='unknown', finished_at=?, error=?,
               handoff_pending=0, handoff_started_at=NULL
           WHERE id=? AND status=? AND process_id=? AND pid=?
             AND handoff_pending=?
             AND handoff_started_at IS ?""",
        (now, reason, row["id"], row["status"], row["process_id"], row["pid"],
         row["handoff_pending"], row["handoff_started_at"]),
    )
    return cur.rowcount == 1


def recover_interrupted_executions() -> int:
    """Mark abandoned attempts unknown without scheduling retries.

    Two classes are released: rows whose owner is provably dead, and rows whose LIVE owner holds
    a claim older than the derived stale bound (a wedged worker, #115692). A wedged owner is
    **terminated** — SIGTERM, then SIGKILL after a grace window — because the alternate reading,
    "release the row but leave the process", leaves exactly the defect this sweep exists to fix:
    the wedged process keeps holding whatever shared lock it took, and a lock outliving its run
    starves every other consumer of that lock. The termination happens between two ledger
    transactions so the ledger lock is never held while waiting on a foreign process.

    Only a pid that still matches the claim's start-time fingerprint is signalled; a recycled
    number is never killed. Rows owned by this process (``process_id == _PROCESS_ID``, in-process
    runs) are skipped and remain out of scope.
    """
    now = _hermes_now().isoformat()
    changed = 0
    recovered: List[Dict[str, Any]] = []
    wedged: List[Dict[str, Any]] = []
    # Derived on the first live-owned row only: the bound reads config, and the idle gateway
    # tick must stay config-free (tests/cron/test_idle_tick_config_skip.py).
    stale_after: Optional[float] = None
    stale_after_resolved = False
    with _transaction() as conn:
        rows = conn.execute(
            """SELECT id, job_id, status, process_id, pid, process_started_at,
                      handoff_pending, handoff_started_at, claimed_at
               FROM executions
               WHERE status IN ('claimed','running')"""
        ).fetchall()
        for row in rows:
            if row["process_id"] == _PROCESS_ID:
                continue
            if _handoff_in_grace(row):
                continue
            if _owner_is_live(int(row["pid"]), row["process_started_at"]):
                # A live owner is normally a legitimately running job. A worker permanently
                # deadlocked (e.g. futex_wait behind a route/proxy flip, #115692) also passes
                # this check, so a claim older than the derived bound is treated as wedged and
                # its owner is terminated after the transaction closes. Deferring the signal
                # keeps the ledger lock out of the SIGTERM grace window.
                if not stale_after_resolved:
                    stale_after = _live_owner_stale_after_seconds()
                    stale_after_resolved = True
                if stale_after is None or _claim_age_seconds(row["claimed_at"]) <= stale_after:
                    continue
                wedged.append(dict(row))
                continue
            if _recover_row(conn, dict(row), _OWNER_GONE_REASON, now):
                changed += 1
                record = _fetch(conn, row["id"])
                if record is not None:
                    recovered.append(record)
        if changed:
            _prune_unlocked(conn)
    for record in recovered:
        _emit_execution_state(record)

    if not wedged:
        return changed

    outcomes: List[tuple] = []
    for row in wedged:
        outcome = terminate_wedged_owner(int(row["pid"]), row["process_started_at"])
        _log_wedged_outcome(row, outcome)
        outcomes.append((row, outcome))

    with _transaction() as conn:
        # Fresh stamp: the termination above may have taken the SIGTERM+SIGKILL grace window, and
        # ``finished_at`` must not predate the death that released the locks.
        wedged_now = _hermes_now().isoformat()
        for row, outcome in outcomes:
            if _recover_row(conn, row, _wedged_reason(outcome), wedged_now):
                changed += 1
                record = _fetch(conn, row["id"])
                if record is not None:
                    recovered.append(record)
        if changed:
            _prune_unlocked(conn)
    for record in recovered:
        _emit_execution_state(record)
    return changed


def list_executions(
    *, job_id: Optional[str] = None, limit: int = 50, before_claimed_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return indexed, newest-first execution history with cursor pagination."""
    clauses: List[str] = []
    params: List[Any] = []
    if job_id is not None:
        clauses.append("job_id=?")
        params.append(str(job_id))
    if before_claimed_at is not None:
        clauses.append("claimed_at < ?")
        params.append(str(before_claimed_at))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(max(1, min(int(limit), 500)))
    with _transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM executions" + where
            + " ORDER BY claimed_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_execution(execution_id: str) -> Optional[Dict[str, Any]]:
    """Return one exact execution attempt, or ``None`` when it is absent."""
    with _transaction() as conn:
        row = conn.execute(
            "SELECT * FROM executions WHERE id=?",
            (str(execution_id),),
        ).fetchone()
    return dict(row) if row is not None else None


def latest_execution(job_id: str) -> Optional[Dict[str, Any]]:
    rows = list_executions(job_id=job_id, limit=1)
    return rows[0] if rows else None


def latest_executions(job_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load latest execution for many jobs in one indexed query."""
    clean = [str(job_id) for job_id in dict.fromkeys(job_ids) if job_id]
    if not clean:
        return {}
    placeholders = ",".join("?" for _ in clean)
    with _transaction() as conn:
        rows = conn.execute(
            f"""SELECT e.* FROM executions e
                WHERE e.job_id IN ({placeholders})
                  AND e.id=(SELECT e2.id FROM executions e2
                            WHERE e2.job_id=e.job_id
                            ORDER BY e2.claimed_at DESC, e2.id DESC LIMIT 1)""",
            clean,
        ).fetchall()
    return {row["job_id"]: dict(row) for row in rows}
