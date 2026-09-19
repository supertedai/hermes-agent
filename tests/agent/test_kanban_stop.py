"""Tests for the kanban worker turn-end stop guard."""

from __future__ import annotations

import pytest

from agent.kanban_stop import (
    BoardState,
    build_kanban_stop_nudge,
    kanban_stop_nudge_enabled,
    probe_board_state,
    session_called_kanban_terminal,
)


@pytest.fixture
def clear_kanban_env(monkeypatch):
    for var in ("HERMES_KANBAN_TASK", "HERMES_KANBAN_STOP_NUDGE"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch






def test_env_can_disable(clear_kanban_env):
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")
    clear_kanban_env.setenv("HERMES_KANBAN_STOP_NUDGE", "0")
    assert kanban_stop_nudge_enabled() is False
    assert build_kanban_stop_nudge(messages=[]) is None


def test_nudge_when_no_terminal_tool(clear_kanban_env):
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_46be8aa5")
    messages = [
        {"role": "user", "content": "work kanban task"},
        {
            "role": "assistant",
            "content": "Let me write the comprehensive recipe.",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "kanban_heartbeat", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "name": "kanban_heartbeat", "tool_call_id": "1", "content": "ok"},
    ]
    nudge = build_kanban_stop_nudge(messages=messages, attempts=0)
    assert nudge is not None
    assert "kanban_complete" in nudge
    assert "kanban_block" in nudge
    assert "t_46be8aa5" in nudge
    assert "protocol violation" in nudge.lower() or "protocol" in nudge.lower()


@pytest.mark.parametrize("tool_name", ["kanban_request_review", "kanban_request_changes"])
def test_no_nudge_after_handoff_tool(clear_kanban_env, tool_name):
    """Review handoffs end the worker's turn exactly like complete/block.

    ``kanban_request_review`` is what a builder is told to call when its work
    needs same-card review; nudging after it asked a worker that did the right
    thing to ``kanban_complete`` a card it must not close (t_f17ea032).
    """
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_handoff")
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "name": tool_name, "tool_call_id": "1", "content": "ok"},
    ]
    assert session_called_kanban_terminal(messages) is True
    assert build_kanban_stop_nudge(messages=messages) is None


# ── Board state is the primary gate ──────────────────────────────────


@pytest.mark.parametrize("status", ["review", "done", "blocked", "archived"])
def test_board_state_left_running_suppresses_nudge(clear_kanban_env, status):
    """A card the board no longer shows as ``running`` has been handed off."""
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")
    nudge = build_kanban_stop_nudge(
        messages=[], board_state=lambda: BoardState(status=status)
    )
    assert nudge is None


def test_board_state_ended_run_suppresses_nudge(clear_kanban_env):
    """A closed run ends this worker's turn whatever the card status says."""
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")
    nudge = build_kanban_stop_nudge(
        messages=[],
        board_state=lambda: BoardState(status="running", run_ended=True),
    )
    assert nudge is None


def test_board_state_running_nudges_and_names_measured_status(clear_kanban_env):
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")
    nudge = build_kanban_stop_nudge(
        messages=[], board_state=lambda: BoardState(status="running")
    )
    assert nudge is not None
    assert "is still `running`" in nudge


def test_unreadable_board_state_falls_back_to_bounded_nudge(clear_kanban_env):
    """No measurement must not become a silent exit, and must not be claimed."""
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")
    probe = lambda: None  # noqa: E731 — unreadable board

    first = build_kanban_stop_nudge(messages=[], attempts=0, board_state=probe)
    second = build_kanban_stop_nudge(messages=[], attempts=1, board_state=probe)
    assert first is not None and second is not None
    assert "is still `running`" not in first
    assert "has not been handed off" in first
    # Bounded exactly as before: 2 attempts, then the guard lets the exit happen.
    assert build_kanban_stop_nudge(messages=[], attempts=2, board_state=probe) is None


def test_probe_exception_falls_back_to_nudge(clear_kanban_env):
    """A probe that raises is an unreadable board, not an exit permit."""
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")

    def boom():
        raise RuntimeError("board unreadable")

    nudge = build_kanban_stop_nudge(messages=[], board_state=boom)
    assert nudge is not None
    assert "is still `running`" not in nudge


def test_default_probe_reads_the_board(clear_kanban_env, tmp_path):
    """The non-injected path must read the real board, not just the transcript.

    Exercises :func:`probe_board_state` against a throwaway kanban DB: the same
    transcript yields a nudge for a ``running`` card and none for a card that
    was handed to ``review``.
    """
    from hermes_cli import kanban_db as kb

    clear_kanban_env.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="guard probe target", assignee="faber")
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (tid,))
        clear_kanban_env.setenv("HERMES_KANBAN_TASK", tid)
        assert probe_board_state(tid) == BoardState(status="running", run_ended=False)
        running_nudge = build_kanban_stop_nudge(messages=[])
        assert running_nudge is not None and "is still `running`" in running_nudge

        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status = 'review' WHERE id = ?", (tid,))
        assert probe_board_state(tid) == BoardState(status="review", run_ended=False)
        assert build_kanban_stop_nudge(messages=[]) is None


def test_probe_reports_unknown_card_as_unreadable(clear_kanban_env, tmp_path):
    """A card the board does not know is unreadable, not "handed off"."""
    clear_kanban_env.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_not_on_this_board")
    assert probe_board_state("t_not_on_this_board") is None
    assert build_kanban_stop_nudge(messages=[]) is not None


def test_no_nudge_after_kanban_complete(clear_kanban_env):
    clear_kanban_env.setenv("HERMES_KANBAN_TASK", "t_abc")
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "kanban_complete", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "name": "kanban_complete", "tool_call_id": "1", "content": "done"},
    ]
    assert session_called_kanban_terminal(messages) is True
    assert build_kanban_stop_nudge(messages=messages) is None






# ── Integration: agent nudge + dispatcher bounded retry ──────────────
# These tests verify the two layers compose correctly: the agent-side
# nudge fires first (up to 2 attempts), and if the worker still exits
# without a terminal call, the dispatcher's bounded retry (streak of 3)
# handles it.  See also tests/hermes_cli/test_kanban_core_functionality.py
# for the dispatcher-side streak tests.




