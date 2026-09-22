"""The delivery journal: one append per delivery decision, at BOTH boundaries.

Why it exists (measured on the house board 2026-09-19, re-measured 2026-09-22):
every ``kanban_notify_subs`` row had moved its cursor (``last_event_id``) and
``last_ping_event_id`` was 0 — which reads as "claim consumed, nothing ever
delivered". Both facts are true, and neither is a delivery failure: the gateway
notifier never touches these rows (no ``tui`` adapter exists), while the
per-session TUI/desktop poller (``tui_gateway.session_notifications``) claims the
same cursor, writes no ping checkpoint, and emits an in-process frame instead of
an adapter send. The cursor moved and the delivery happened; nothing recorded it.

These tests lock the INSTRUMENT, not the delivery policy: a claim, a skip, a send
and a policy suppression each leave a row naming the boundary that took the
decision, so "no event" / "wrong classification" / "suppressed" / "digest" /
"delivery failure" can be told apart afterwards. See ADR-088 decision 4.
"""

import asyncio
import logging

import pytest

import gateway.kanban_watchers_notifier as notifier
from gateway.config import Platform
from gateway.platforms.base import SendResult
from gateway.run import GatewayRunner
from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_db_notify as kbn
from tui_gateway.server import _collect_kanban_notifications

TUI_SESSION_KEY = "tui-session-key-1"


class RecordingAdapter:
    """A push adapter that hands back a receipt, like a real send does."""

    def __init__(self, *, message_id="msg-1", error=None):
        self.sent = []
        self.message_id = message_id
        self.error = error

    async def send(self, chat_id, text, metadata=None):
        self.sent.append({"chat_id": chat_id, "text": text, "metadata": metadata or {}})
        if self.error:
            raise RuntimeError(self.error)
        return SendResult(success=True, message_id=self.message_id)


@pytest.fixture(autouse=True)
def _per_process_dedupe_sets(monkeypatch):
    """The warn/skip dedupe sets are per process on purpose — a test IS a process."""
    monkeypatch.setattr(notifier, "_NO_ADAPTER_WARNED", set())
    monkeypatch.setattr(notifier, "_SKIP_JOURNALED", set())
    monkeypatch.setattr(notifier, "_NO_ADAPTERS_WARNED", False)
    monkeypatch.setattr(kbn, "_JOURNAL_WRITE_FAILED_LOGGED", False)


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "board.db"))
    kb.init_db()
    return tmp_path


def _rows(task_id=None, limit=200):
    conn = kbc.connect()
    try:
        return kbn.notify_journal_rows(conn, task_id=task_id, limit=limit)
    finally:
        conn.close()


def _outcomes(task_id=None):
    return [(row["phase"], row["outcome"]) for row in _rows(task_id)]


def _subs(task_id):
    conn = kbc.connect()
    try:
        return kbn.list_notify_subs(conn, task_id=task_id)
    finally:
        conn.close()


def _make_runner(adapter):
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._running = True
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._kanban_sub_fail_counts = {}
    runner._kanban_dispatcher_lock_handle = object()
    return runner


async def _run_one_notifier_tick(monkeypatch, runner):
    real_sleep = asyncio.sleep

    async def fake_sleep(delay):
        if delay == 5:
            return None
        runner._running = False
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await runner._kanban_notifier_watcher(interval=1)


def _create_subscription(platform="telegram", chat_id="chat-1", *, complete=True, archive=False, title="journal once"):
    conn = kbc.connect()
    try:
        tid = kb.create_task(conn, title=title, assignee="worker")
        kbn.add_notify_sub(conn, task_id=tid, platform=platform, chat_id=chat_id)
        if complete:
            kb.complete_task(conn, tid, summary="done")
        if archive:
            kb.archive_task(conn, tid)
        return tid
    finally:
        conn.close()


# --- schema and the journal API ------------------------------------------------


def test_fresh_board_carries_the_journal_table(board):
    conn = kbc.connect()
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "kanban_notify_journal" in names


def test_an_existing_board_is_migrated_to_the_journal_table(board):
    """A board created before this table existed gains it on the next connect."""
    conn = kbc.connect()
    try:
        conn.execute("DROP TABLE kanban_notify_journal")
        conn.commit()
    finally:
        conn.close()
    kbc._INITIALIZED_PATHS.discard(str((board / "board.db").resolve()))

    conn = kbc.connect()
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "kanban_notify_journal" in names


def test_one_row_per_claimed_event_records_the_cursor_move(board):
    tid = _create_subscription(complete=True)
    conn = kbc.connect()
    try:
        events = kbn.unseen_events_for_sub(
            conn, task_id=tid, platform="telegram", chat_id="chat-1", kinds=["completed"])[1]
        written = kbn.journal_notify_claim(
            conn, task_id=tid, platform="telegram", chat_id="chat-1", dispatcher="gateway",
            events=events, cursor_before=0, cursor_after=events[-1].id, delivery_mode="notify")
    finally:
        conn.close()

    assert written == len(events) == 1
    row = _rows(tid)[0]
    assert (row["phase"], row["outcome"], row["dispatcher"]) == ("claim", "claimed", "gateway")
    assert row["event_id"] == events[-1].id
    assert row["kind"] == "completed"
    assert row["cursor_after"] == events[-1].id
    assert row["delivery_mode"] == "notify"
    assert row["created_at"] > 0


def test_a_journal_row_is_never_rewritten(board):
    """Append-only: a retry writes a new row and leaves the earlier one intact."""
    tid = _create_subscription(complete=True)
    conn = kbc.connect()
    try:
        kbn.journal_notify_decision(conn, task_id=tid, platform="telegram", chat_id="chat-1",
                                    dispatcher="gateway", phase="deliver", outcome="send_failed",
                                    event_id=1, kind="completed", send_result="failed: boom")
        kbn.journal_notify_decision(conn, task_id=tid, platform="telegram", chat_id="chat-1",
                                    dispatcher="gateway", phase="deliver", outcome="sent",
                                    event_id=1, kind="completed", send_result="ok", receipt="msg-9")
    finally:
        conn.close()

    assert _outcomes(tid) == [("deliver", "send_failed"), ("deliver", "sent")]


def test_the_journal_write_failure_never_raises(board):
    conn = kbc.connect()
    try:
        conn.execute("DROP TABLE kanban_notify_journal")
        conn.commit()
        written = kbn.journal_notify_decision(
            conn, task_id="t_x", platform="telegram", chat_id="c", dispatcher="gateway",
            phase="deliver", outcome="sent")
    finally:
        conn.close()
    assert written == 0


def test_prune_drops_only_rows_past_retention(board):
    tid = _create_subscription(complete=True)
    conn = kbc.connect()
    try:
        kbn.journal_notify_decision(conn, task_id=tid, platform="telegram", chat_id="chat-1",
                                    dispatcher="gateway", phase="deliver", outcome="sent")
        conn.execute("UPDATE kanban_notify_journal SET created_at = created_at - 30 * 86400")
        conn.commit()
        kbn.journal_notify_decision(conn, task_id=tid, platform="telegram", chat_id="chat-1",
                                    dispatcher="gateway", phase="deliver", outcome="sent")
        assert kbn.prune_notify_journal(conn, max_age_days=14) == 1
    finally:
        conn.close()
    assert _outcomes(tid) == [("deliver", "sent")]


def test_rows_are_read_back_newest_last_and_filtered_by_task(board):
    first = _create_subscription(complete=True, title="first")
    second = _create_subscription(complete=True, title="second")
    conn = kbc.connect()
    try:
        for tid, receipt in ((first, "a"), (second, "b"), (first, "c")):
            kbn.journal_notify_decision(conn, task_id=tid, platform="telegram", chat_id="chat-1",
                                        dispatcher="gateway", phase="deliver", outcome="sent", receipt=receipt)
    finally:
        conn.close()

    assert [row["receipt"] for row in _rows(first)] == ["a", "c"]
    assert [row["receipt"] for row in _rows(first)][-1] == "c"


# --- the gateway boundary: where adapter.send() is and is not called -----------


def test_a_sent_ping_is_journaled_with_its_receipt(board, monkeypatch):
    tid = _create_subscription(complete=True)
    adapter = RecordingAdapter(message_id="msg-42")
    asyncio.run(_run_one_notifier_tick(monkeypatch, _make_runner(adapter)))

    assert len(adapter.sent) == 1, "the delivery behaviour itself is unchanged"
    rows = _rows(tid)
    claim = [r for r in rows if r["phase"] == "claim"]
    sent = [r for r in rows if r["outcome"] == "sent"]
    assert len(claim) == 1 and len(sent) == 1
    assert sent[0]["dispatcher"] == "gateway"
    assert sent[0]["receipt"] == "msg-42", "the row is matchable against the channel message"
    assert sent[0]["attempted_at"] and sent[0]["attempted_at"] >= sent[0]["created_at"] - 60
    assert sent[0]["cursor_after"] == claim[0]["cursor_after"], "the row ties to the cursor it settled"


def test_a_silent_kind_is_on_the_record_as_a_skip_not_a_delivery(board, monkeypatch):
    """``archived`` is claimed (cursor moves) and has no formatter: nothing is sent."""
    tid = _create_subscription(complete=False, archive=True)
    adapter = RecordingAdapter()
    asyncio.run(_run_one_notifier_tick(monkeypatch, _make_runner(adapter)))

    assert adapter.sent == []
    outcomes = _outcomes(tid)
    assert ("claim", "claimed") in outcomes
    assert ("deliver", "skipped_silent_kind") in outcomes
    assert not any(outcome in {"sent", "send_failed"} for _, outcome in outcomes)


def test_a_subscription_with_no_adapter_is_journaled_and_warned_once(board, monkeypatch, caplog):
    tid = _create_subscription(platform="tui", chat_id=TUI_SESSION_KEY, complete=True)
    cursor_before = _subs(tid)[0]["last_event_id"]
    adapter = RecordingAdapter()
    runner = _make_runner(adapter)

    with caplog.at_level(logging.WARNING, logger="gateway.run"):
        asyncio.run(_run_one_notifier_tick(monkeypatch, runner))
        runner._running = True
        asyncio.run(_run_one_notifier_tick(monkeypatch, runner))

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "once per platform per process, not once per tick"
    assert "tui" in warnings[0] and "subscription(s)" in warnings[0]
    assert adapter.sent == []

    rows = _rows(tid)
    assert [r["outcome"] for r in rows] == ["skipped_no_adapter"], "one row per subscription, not per tick"
    assert rows[0]["phase"] == "skip" and rows[0]["dispatcher"] == "gateway"
    assert rows[0]["event_id"] is None
    assert rows[0]["cursor_before"] is None and rows[0]["cursor_after"] is None
    # The skip is a claim-time refusal: the cursor is untouched, which is exactly
    # what distinguishes it from a delivery that moved the cursor.
    assert _subs(tid)[0]["last_event_id"] == cursor_before


def test_a_gateway_with_no_adapters_warns_once(board, monkeypatch, caplog):
    tid = _create_subscription(complete=True)
    runner = _make_runner(RecordingAdapter())
    runner.adapters = {}

    with caplog.at_level(logging.WARNING, logger="gateway.run"):
        asyncio.run(_run_one_notifier_tick(monkeypatch, runner))
        runner._running = True
        asyncio.run(_run_one_notifier_tick(monkeypatch, runner))

    warnings = [r.getMessage() for r in caplog.records
                if r.levelno == logging.WARNING and "no connected adapters" in r.getMessage()]
    assert len(warnings) == 1
    assert _rows(tid) == []


def test_a_failed_send_is_journaled_and_the_claim_rewinds(board, monkeypatch, caplog):
    tid = _create_subscription(complete=True)
    adapter = RecordingAdapter(error="chat is gone")
    with caplog.at_level(logging.WARNING, logger="gateway.run"):
        asyncio.run(_run_one_notifier_tick(monkeypatch, _make_runner(adapter)))

    rows = _rows(tid)
    failed = [r for r in rows if r["outcome"] == "send_failed"]
    claim = [r for r in rows if r["phase"] == "claim"]
    assert len(failed) == 1 and len(claim) == 1
    assert "chat is gone" in failed[0]["send_result"]
    assert failed[0]["cursor_after"] == claim[0]["cursor_before"], "the rewind returns the cursor to the pre-claim value"
    assert failed[0]["receipt"] is None
    assert _subs(tid)[0]["last_event_id"] == claim[0]["cursor_before"], "the next tick retries"
    assert _subs(tid)[0]["last_event_id"] < claim[0]["cursor_after"], "the claim did move it before the rewind"


def test_a_suppressed_diagnostic_is_journaled_as_suppressed(board, monkeypatch):
    """The warning-notification policy is a delivery decision, not a silence."""
    tid = _create_subscription(complete=True)
    import gateway.warning_notifications as warning_notifications

    async def _never_present(present, *, platform, diagnostic=True, user_config=None):
        """Stand-in for a platform with display.<platform>.suppress_warning_notifications."""
        return False

    monkeypatch.setattr(warning_notifications, "present_notification", _never_present)
    adapter = RecordingAdapter()
    asyncio.run(_run_one_notifier_tick(monkeypatch, _make_runner(adapter)))

    assert adapter.sent == []
    assert ("deliver", "suppressed_by_policy") in _outcomes(tid)


def test_the_tui_poller_records_a_claim_it_renders_nowhere(board):
    """A claimed event with no formatter is the silent hole, and it is now visible."""
    tid = _create_subscription(platform="tui", chat_id=TUI_SESSION_KEY, complete=False, archive=True)

    texts = _collect_kanban_notifications(_tui_session())

    assert texts == []
    assert ("deliver", "skipped_silent_kind") in _outcomes(tid)


def test_a_broken_journal_never_stops_a_delivery(board, monkeypatch, caplog):
    tid = _create_subscription(complete=True)
    conn = kbc.connect()
    try:
        conn.execute("DROP TABLE kanban_notify_journal")
        conn.commit()
    finally:
        conn.close()
    adapter = RecordingAdapter(message_id="msg-7")

    with caplog.at_level(logging.WARNING, logger="gateway.run"):
        asyncio.run(_run_one_notifier_tick(monkeypatch, _make_runner(adapter)))

    assert len(adapter.sent) == 1, "the send happens regardless of the journal"
    assert _subs(tid)[0]["last_ping_event_id"] > 0, "the ping checkpoint is still recorded"


# --- the TUI boundary: the path that moves the cursor with no adapter ----------


def _tui_session(key=TUI_SESSION_KEY):
    return {"session_key": key}


def test_the_tui_poller_journals_its_claim_and_its_frame(board):
    tid = _create_subscription(platform="tui", chat_id=TUI_SESSION_KEY, complete=True)

    texts = _collect_kanban_notifications(_tui_session())

    assert len(texts) == 1, "the in-process delivery itself is unchanged"
    rows = _rows(tid)
    assert [r["dispatcher"] for r in rows] == ["tui", "tui"]
    assert [(r["phase"], r["outcome"]) for r in rows] == [("claim", "claimed"), ("deliver", "in_process_frame")]
    assert rows[1]["reason"].startswith("queued for this session's own status.update frame")


def test_the_measured_shape_is_explained_by_the_journal(board):
    """The 2026-09-19 measurement, reproduced and explained.

    Cursor moved, ping checkpoint 0, nothing in any gateway surface — and the
    journal is what says where the delivery went instead of leaving it as the
    inference "claimed but never sent".
    """
    tid = _create_subscription(platform="tui", chat_id=TUI_SESSION_KEY, complete=True)

    _collect_kanban_notifications(_tui_session())

    sub = _subs(tid)[0]
    assert sub["last_event_id"] > 0, "the cursor moved"
    assert sub["last_ping_event_id"] == 0, "no ping checkpoint was ever written"
    delivered = [r for r in _rows(tid) if r["outcome"] == "in_process_frame"]
    assert delivered and delivered[0]["dispatcher"] == "tui"
    assert delivered[0]["event_id"] == sub["last_event_id"], "the row names the event the cursor points at"
