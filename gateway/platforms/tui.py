"""Built-in local TUI delivery adapter for cron origin messages."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request as UrlRequest, urlopen

from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter, SendResult


def check_tui_requirements() -> bool:
    return True


def validate_tui_config(_config: Any) -> bool:
    return True


def _resolve_session_id(server: Any, requested: str) -> str:
    sessions = getattr(server, "_sessions", {})
    direct = sessions.get(requested)
    def _is_owned_tui_session(session: Any) -> bool:
        if not isinstance(session, dict):
            return False
        if session.get("transport") is None or session.get("running") is False:
            return False
        identity = str(
            session.get("owner")
            or session.get("user_id")
            or session.get("source")
            or ""
        ).strip().lower()
        return identity in {"morten", "tui"}

    if _is_owned_tui_session(direct):
        return requested
    candidates = [
        (sid, session)
        for sid, session in sessions.items()
        if _is_owned_tui_session(session)
    ]
    if requested in {"morten", "tui"} and len(candidates) == 1:
        return candidates[0][0]
    return ""


class TUIAdapter(BasePlatformAdapter):
    """Adapter facade; live delivery uses the TUI gateway session transport.

    The TUI is local and does not open an external listener.  It still
    implements the normal BasePlatformAdapter lifecycle so the gateway can
    register it, connect it, and route generic sends without special cases.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config, Platform("tui"))

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        self._running = True
        return True

    async def disconnect(self) -> None:
        self._running = False

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        from tui_gateway import server

        session_id = _resolve_session_id(server, str(chat_id or "").strip())
        session = getattr(server, "_sessions", {}).get(session_id)
        if not session or session.get("transport") is None:
            return {"name": "Hermes TUI", "type": "dm", "connected": False}
        return {"name": "Hermes TUI", "type": "dm", "connected": True, "session_id": session_id}

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        result = await self.send_message(
            chat_id,
            content,
            thread_id=(metadata or {}).get("thread_id"),
        )
        if result.get("success"):
            return SendResult(success=True, message_id=result.get("message_id"), raw_response=result)
        return SendResult(success=False, error=result.get("error", "TUI delivery failed"), raw_response=result)

    @staticmethod
    def _relay_config() -> tuple[str, str]:
        url = os.getenv("HERMES_TUI_RELAY_URL", "http://127.0.0.1:9119/api/internal/tui/emit")
        secret_path = Path(os.getenv("HERMES_TUI_RELAY_SECRET_FILE", "~/.hermes-gui/tui-relay.secret")).expanduser()
        try:
            secret = secret_path.read_text(encoding="utf-8").strip()
        except OSError:
            secret = ""
        return url, secret

    async def _relay_send(self, chat_id: str, message: str, thread_id: str | None) -> dict[str, Any]:
        url, secret = self._relay_config()
        if not secret:
            return {"error": "tui_session_not_connected", "session_id": chat_id}
        payload = {
            "chat_id": chat_id,
            "text": message,
            "source": "faber",
            "thread_id": thread_id,
            "message_id": uuid.uuid4().hex[:12],
        }

        def _post() -> dict[str, Any]:
            request = UrlRequest(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Hermes-TUI-Relay-Secret": secret},
                method="POST",
            )
            try:
                with urlopen(request, timeout=5) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code in {401, 404}:
                    return {"error": "tui_session_not_connected", "session_id": chat_id}
                return {"error": f"tui_relay_failed:{type(exc).__name__}", "detail": str(exc)}

        return await asyncio.to_thread(_post)

    async def send_message(self, chat_id: str, message: str, *, thread_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        from tui_gateway import server

        session_id = _resolve_session_id(server, str(chat_id or "").strip())
        session = getattr(server, "_sessions", {}).get(session_id)
        if not session or session.get("transport") is None:
            return await self._relay_send(str(chat_id or "").strip(), message, thread_id)
        payload = {
            "message_id": uuid.uuid4().hex[:12],
            "text": message,
            "source": "faber",
            "thread_id": thread_id,
        }
        server._emit("cron.message", session_id, payload)
        return {"success": True, "message_id": payload["message_id"], "session_id": session_id}


async def standalone_send(
    pconfig: Any,
    chat_id: str,
    message: str,
    *,
    thread_id: str | None = None,
    media_files: list[str] | None = None,
    force_document: bool = False,
) -> dict[str, Any]:
    return await TUIAdapter(pconfig).send_message(chat_id, message, thread_id=thread_id)


def register() -> None:
    from gateway.platform_registry import PlatformEntry, platform_registry

    platform_registry.register(PlatformEntry(
        name="tui",
        label="Hermes TUI",
        adapter_factory=lambda cfg: TUIAdapter(cfg),
        check_fn=check_tui_requirements,
        validate_config=validate_tui_config,
        standalone_sender_fn=standalone_send,
        source="builtin",
        emoji="🖥️",
        platform_hint="Deliver Faber readback to the active Hermes TUI session.",
        allow_update_command=False,
    ))


register()
