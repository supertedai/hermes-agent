"""Turn-end guard for kanban workers.

Kanban workers must end with a board tool that hands the card to whoever owns
it next (``kanban_complete``, ``kanban_block``, ``kanban_request_review``).
Models (especially GLM / Qwen families) sometimes narrate the next step
("Let me write the report now") and stop with ``finish_reason=stop`` and no
tool calls. Hermes treats that as a clean exit → ``rc=0`` → dispatcher
``protocol_violation``.

This module is policy-only: when a kanban worker tries to finish without a
terminal board tool, return a bounded synthetic nudge so the conversation
loop continues instead of exiting. Before it nudges, it reads the card's board
state (best effort): a card that has already left ``running`` — e.g. one sent
to ``review`` — must never be nudged towards closing itself out.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional


# Every tool that ends THIS worker's responsibility for the card, not just the
# two that close it out. ``kanban_request_review`` moves the card to ``review``
# and is the call a builder is *told* to make when the work needs same-card
# review; ``kanban_request_changes`` is the same handoff one step later
# (reviewer → ``ready``). Nudging after either asks a worker that did the right
# thing to ``kanban_complete`` a card it must not close.
# Measured 2026-09-18 (t_f17ea032): the guard fired on a worker that had just
# called ``kanban_request_review``, and pushed it towards ``kanban_complete``.
_TERMINAL_KANBAN_TOOLS = frozenset({
    "kanban_complete",
    "kanban_block",
    "kanban_request_review",
    "kanban_request_changes",
})

_DEFAULT_MAX_ATTEMPTS = 2

_RUNNING_STATUS = "running"


@dataclass(frozen=True)
class BoardState:
    """Measured board state of the worker's own card."""

    status: str
    # True when the card's current run has already been closed. The dispatcher
    # stamps ``ended_at`` on complete / block / review-handoff / crash, so a
    # closed run means this worker's turn is over whatever the card status says.
    run_ended: bool = False

    @property
    def worker_still_owns_card(self) -> bool:
        """True only while the card is ``running`` under a run that is still open."""
        return (
            self.status.strip().lower() == _RUNNING_STATUS
            and not self.run_ended
        )


# A probe returns the measured state, or ``None`` when the state cannot be read.
BoardStateProbe = Callable[[], Optional[BoardState]]


def probe_board_state(task_id: Optional[str] = None) -> Optional[BoardState]:
    """Best-effort read of the card's board state; ``None`` when unreadable.

    Reads the dispatcher-pinned kanban DB (``HERMES_KANBAN_DB``, resolved by
    :func:`hermes_cli.kanban_db.kanban_db_path`) for the card's status and
    whether its current run is closed.

    Every failure — no DB, unknown card, any exception (including a test
    suite's kanban write guard refusing the path) — collapses to ``None`` so
    the caller falls back to its transcript-only decision instead of failing
    open. This runs in the worker process at turn end: it must never raise and
    never block on the board.
    """
    tid = (task_id or os.environ.get("HERMES_KANBAN_TASK") or "").strip()
    if not tid:
        return None
    try:
        from hermes_cli import kanban_db as kb

        with kb.connect_closing() as conn:
            row = conn.execute(
                "SELECT t.status AS status, r.ended_at AS ended_at "
                "FROM tasks t LEFT JOIN task_runs r ON r.id = t.current_run_id "
                "WHERE t.id = ?",
                (tid,),
            ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    try:
        status = str(row["status"] or "")
        ended_at = row["ended_at"]
    except Exception:
        return None
    if not status:
        return None
    return BoardState(status=status, run_ended=ended_at is not None)


def kanban_stop_nudge_enabled() -> bool:
    """Return whether the kanban stop-guard is active for this process.

    On when ``HERMES_KANBAN_TASK`` is set (dispatcher-spawned worker), unless
    ``HERMES_KANBAN_STOP_NUDGE`` explicitly disables it.
    """
    env = os.environ.get("HERMES_KANBAN_STOP_NUDGE")
    if env is not None and env.strip().lower() in {"0", "false", "no", "off"}:
        return False
    task = (os.environ.get("HERMES_KANBAN_TASK") or "").strip()
    return bool(task)


def _tool_call_name(tc: Any) -> str:
    if isinstance(tc, dict):
        fn = tc.get("function")
        if isinstance(fn, dict):
            return str(fn.get("name") or "")
        return str(tc.get("name") or "")
    fn = getattr(tc, "function", None)
    if fn is not None:
        return str(getattr(fn, "name", "") or "")
    return str(getattr(tc, "name", "") or "")


def session_called_kanban_terminal(messages: Iterable[dict] | None) -> bool:
    """True if this conversation already invoked a terminal kanban tool."""
    if not messages:
        return False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                if _tool_call_name(tc) in _TERMINAL_KANBAN_TOOLS:
                    return True
        elif role == "tool":
            name = str(msg.get("name") or "")
            if name in _TERMINAL_KANBAN_TOOLS:
                return True
    return False


def build_kanban_stop_nudge(
    *,
    messages: Iterable[dict] | None = None,
    attempts: int = 0,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    task_id: Optional[str] = None,
    board_state: Optional[BoardStateProbe] = None,
) -> Optional[str]:
    """Return a synthetic follow-up when a kanban worker exits without a terminal tool.

    Returns ``None`` when the guard should not fire: not a kanban worker, nudge
    budget exhausted, the transcript already carries a handoff call, or the
    board shows the card left ``running`` (``review``, ``done``, …) or its run
    already ended.

    ``board_state`` is an injectable probe (``() -> BoardState | None``) for
    callers that already hold the state. When omitted, the board is read
    best-effort through :func:`probe_board_state`; an unreadable board falls
    back to the transcript-only decision — never to a silent exit.
    """
    if not kanban_stop_nudge_enabled():
        return None
    if attempts >= max_attempts:
        return None
    if session_called_kanban_terminal(messages):
        return None

    tid = (task_id or os.environ.get("HERMES_KANBAN_TASK") or "").strip() or "this task"

    # Board state is the primary gate. A card that already left ``running`` —
    # or whose run is closed — has been handed off, whatever this transcript
    # shows; the handoff tool may have been called in a way this module does not
    # match. ``None`` means "not measured" and falls through to the
    # transcript-only decision below: the guard never fails open.
    measured: Optional[BoardState] = None
    try:
        measured = board_state() if board_state is not None else probe_board_state(tid)
    except Exception:
        measured = None
    if measured is not None and not measured.worker_still_owns_card:
        return None

    if measured is None:
        # Unmeasured: never claim a state we could not read. The transcript has
        # no handoff call, so the card is at best still owed one.
        state_claim = (
            f"Task `{tid}` has not been handed off: this session made no "
            "terminal board call, and the board state could not be read."
        )
    else:
        # Only reachable for status ``running`` under an open run — every other
        # measured state returned ``None`` above — so this claim is the state
        # that was actually read.
        state_claim = f"Task `{tid}` is still `{measured.status}`."
    return (
        "[System: You are a Hermes kanban worker. A plain-text reply is NOT a "
        "terminal state for the board.\n\n"
        f"{state_claim} Ending now causes a protocol violation (clean exit "
        "with the card not handed off).\n\n"
        "Do this immediately in your next response — do not narrate intent:\n"
        "1. Finish any remaining deliverable (write the required file(s) now).\n"
        "2. Call `kanban_complete(summary=..., artifacts=[...])` if the work "
        "is done and needs no review, `kanban_request_review(summary=...)` if "
        "it is a code change that needs same-card review, OR "
        "`kanban_block(reason=...)` if you are blocked.\n\n"
        "Never end a turn with only a promise of future action. Repeated "
        "protocol violations will block this task and require manual intervention.]"
    )


__all__ = [
    "BoardState",
    "BoardStateProbe",
    "build_kanban_stop_nudge",
    "kanban_stop_nudge_enabled",
    "probe_board_state",
    "session_called_kanban_terminal",
]
