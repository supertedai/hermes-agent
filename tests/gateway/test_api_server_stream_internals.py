"""Tests for the gated internal-progress SSE mapping (BL-2506).

``_map_internal_progress_event`` decides which raw agent progress events are
forwarded on the /v1/chat/completions channel when a first-party client opts
in via the X-Hermes-Stream-Internals header.  The event shapes asserted here
mirror the emit sites in ``tools/delegate_tool`` and the canonical consumer
``tools/delegation_live_log.observe`` — keep them in sync if those change.
"""

from gateway.platforms.api_server import (
    _flag_is_truthy,
    _map_internal_progress_event,
)


class TestFlagIsTruthy:
    def test_affirmative_spellings(self):
        for v in ("1", "true", "TRUE", "Yes", "on", " on "):
            assert _flag_is_truthy(v) is True

    def test_falsey_or_absent(self):
        for v in (None, "", "0", "false", "no", "off", "maybe"):
            assert _flag_is_truthy(v) is False


class TestToolEventsAreDropped:
    """Tool lifecycle events are owned by the structured callbacks — the
    progress channel must never re-forward them (would duplicate every tool)."""

    def test_tool_started_dropped(self):
        assert _map_internal_progress_event("tool.started", "web_search", "query") is None

    def test_tool_completed_dropped(self):
        assert _map_internal_progress_event("tool.completed", "web_search", duration=1.2) is None

    def test_tool_failed_dropped(self):
        assert _map_internal_progress_event("tool.failed", "web_search") is None

    def test_unknown_event_dropped(self):
        assert _map_internal_progress_event("subagent.spawn_requested", preview="goal") is None

    def test_empty_event_dropped(self):
        assert _map_internal_progress_event("") is None


class TestThinkingMapping:
    def test_thinking_text_rides_in_tool_name_slot(self):
        # cb("_thinking", <text>)  → text lands in the tool_name positional slot
        tag, payload = _map_internal_progress_event("_thinking", "pondering the graph")
        assert tag == "__hermes_thinking__"
        assert payload == {"scope": "agent", "delta": "pondering the graph"}

    def test_reasoning_available_text_rides_in_preview(self):
        # cb("reasoning.available", "_thinking", <text>, None)
        tag, payload = _map_internal_progress_event(
            "reasoning.available", "_thinking", "deep reasoning text"
        )
        assert tag == "__hermes_thinking__"
        assert payload == {"scope": "agent", "delta": "deep reasoning text"}

    def test_empty_thinking_dropped(self):
        assert _map_internal_progress_event("_thinking", "") is None
        assert _map_internal_progress_event("reasoning.available", "_thinking", "   ") is None


class TestSubagentMapping:
    def test_start(self):
        tag, payload = _map_internal_progress_event("subagent.start", preview="research EFC")
        assert tag == "__hermes_subagent__"
        assert payload == {"phase": "start", "text": "research EFC"}

    def test_text(self):
        tag, payload = _map_internal_progress_event("subagent.text", preview="found 3 hits")
        assert tag == "__hermes_subagent__"
        assert payload == {"phase": "text", "text": "found 3 hits"}

    def test_thinking(self):
        tag, payload = _map_internal_progress_event("subagent.thinking", preview="comparing")
        assert payload == {"phase": "thinking", "text": "comparing"}

    def test_tool(self):
        tag, payload = _map_internal_progress_event("subagent.tool", "graph_query", "MATCH ...")
        assert payload == {"phase": "tool", "tool": "graph_query", "text": "MATCH ..."}

    def test_progress_structured(self):
        tag, payload = _map_internal_progress_event("subagent.progress", preview="🔀 [1] step")
        assert payload == {"phase": "progress", "text": "🔀 [1] step"}

    def test_progress_legacy_summary_in_tool_name_slot(self):
        # Legacy: cb("subagent_progress", <summary>) → summary in tool_name slot
        tag, payload = _map_internal_progress_event("subagent_progress", "🔀 [1] terminal, file")
        assert tag == "__hermes_subagent__"
        assert payload == {"phase": "progress", "text": "🔀 [1] terminal, file"}

    def test_complete_carries_status_duration_summary(self):
        tag, payload = _map_internal_progress_event(
            "subagent.complete",
            preview=None,
            status="ok",
            duration_seconds=4.1,
            summary="returned 3 findings",
        )
        assert tag == "__hermes_subagent__"
        assert payload == {
            "phase": "complete",
            "status": "ok",
            "duration": 4.1,
            "summary": "returned 3 findings",
        }

    def test_complete_falls_back_to_preview_summary(self):
        tag, payload = _map_internal_progress_event(
            "subagent.complete", preview="done-ish", status="ok"
        )
        assert payload["summary"] == "done-ish"
        assert payload["duration"] is None
