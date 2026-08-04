from __future__ import annotations

import asyncio

from gateway.config import Platform
from gateway.platform_registry import platform_registry
from gateway.platforms.tui import TUIAdapter


class _Transport:
    def __init__(self):
        self.frames = []

    def write(self, frame):
        self.frames.append(frame)


def test_tui_platform_is_registered_and_emits_to_active_session(monkeypatch):
    import tui_gateway.server as server

    transport = _Transport()
    monkeypatch.setitem(server._sessions, "sid-1", {"transport": transport, "owner": "morten"})
    assert Platform("tui").value == "tui"
    assert platform_registry.is_registered("tui")
    result = asyncio.run(TUIAdapter(None).send_message("sid-1", "Faber readback"))
    assert result["success"] is True
    assert transport.frames[0]["method"] == "event"
    assert transport.frames[0]["params"]["type"] == "cron.message"
    assert transport.frames[0]["params"]["session_id"] == "sid-1"
    assert transport.frames[0]["params"]["payload"]["source"] == "faber"
    transport.frames.clear()
    alias_result = asyncio.run(TUIAdapter(None).send_message("morten", "Alias readback"))
    assert alias_result["success"] is True
    assert transport.frames[0]["params"]["session_id"] == "sid-1"


def test_tui_platform_accepts_real_source_bound_session(monkeypatch):
    import tui_gateway.server as server

    transport = _Transport()
    monkeypatch.setitem(server._sessions, "source-tui", {"transport": transport, "source": "tui"})
    result = asyncio.run(TUIAdapter(None).send_message("source-tui", "source-bound readback"))
    assert result["success"] is True
    assert result["session_id"] == "source-tui"


def test_tui_platform_rejects_stopped_or_unowned_alias_sessions(monkeypatch):
    import tui_gateway.server as server

    transport = _Transport()
    monkeypatch.setitem(server._sessions, "stopped", {"transport": transport, "running": False, "owner": "morten"})
    monkeypatch.setitem(server._sessions, "unowned", {"transport": transport, "owner": "other"})

    async def no_remote_relay(self, chat_id, message, thread_id):
        return {"error": "tui_session_not_connected", "session_id": chat_id}

    monkeypatch.setattr(TUIAdapter, "_relay_send", no_remote_relay)
    stopped = asyncio.run(TUIAdapter(None).send_message("stopped", "must not deliver"))
    assert stopped == {"error": "tui_session_not_connected", "session_id": "stopped"}
    alias = asyncio.run(TUIAdapter(None).send_message("morten", "must not guess"))
    assert alias == {"error": "tui_session_not_connected", "session_id": "morten"}
    assert transport.frames == []


def test_tui_platform_rejects_direct_session_without_owner_binding(monkeypatch):
    import tui_gateway.server as server

    transport = _Transport()
    monkeypatch.setitem(server._sessions, "known-but-unowned", {"transport": transport})
    result = asyncio.run(TUIAdapter(None).send_message("known-but-unowned", "must not deliver"))
    assert result == {"error": "tui_session_not_connected", "session_id": "known-but-unowned"}
    assert transport.frames == []


def test_tui_platform_fails_closed_without_active_session():
    result = asyncio.run(TUIAdapter(None).send_message("missing-session", "Faber readback"))
    assert result == {"error": "tui_session_not_connected", "session_id": "missing-session"}
