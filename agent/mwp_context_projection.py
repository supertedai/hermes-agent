"""Metadata-only validation for Chat ↔ Cortex ↔ shared-world-model readbacks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


class ContextVerdict(str):
    COMPLETE = "COMPLETE"
    UNVERIFIED = "UNVERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ContextReadback:
    conversation_id: str
    user_id: str
    working_model_ref: str
    cortex_ref: str
    agent_id: str
    agent_role: str
    agent_binding_ref: str
    handoff_ref: str
    recorded_at: str
    freshness_seconds: int | None
    provenance: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "working_model_ref": self.working_model_ref,
            "cortex_ref": self.cortex_ref,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "agent_binding_ref": self.agent_binding_ref,
            "handoff_ref": self.handoff_ref,
            "recorded_at": self.recorded_at,
            "freshness_seconds": self.freshness_seconds,
            "provenance": list(self.provenance),
            "raw_payload_included": False,
        }


def validate_context_readback(
    readback: Mapping[str, Any],
    *,
    now: datetime,
    max_freshness_seconds: int = 900,
) -> tuple[str, tuple[str, ...]]:
    """Return a fail-closed verdict and blockers, never a content payload."""
    required = (
        "conversation_id", "user_id", "working_model_ref", "cortex_ref",
        "agent_id", "agent_role", "agent_binding_ref", "handoff_ref", "recorded_at",
    )
    missing = tuple(key for key in required if not str(readback.get(key) or "").strip())
    if missing:
        return ContextVerdict.BLOCKED, tuple(f"missing {key}" for key in missing)
    provenance = readback.get("provenance")
    if not isinstance(provenance, list) or not provenance or not all(str(item).strip() for item in provenance):
        return ContextVerdict.BLOCKED, ("provenance missing or invalid",)
    freshness = readback.get("freshness_seconds")
    if not isinstance(freshness, int) or freshness < 0:
        return ContextVerdict.UNVERIFIED, ("freshness_seconds missing or invalid",)
    if freshness > max_freshness_seconds:
        return ContextVerdict.UNVERIFIED, ("context readback stale",)
    try:
        recorded = datetime.fromisoformat(str(readback["recorded_at"]).replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        if recorded > now.astimezone(timezone.utc):
            return ContextVerdict.UNVERIFIED, ("recorded_at is in the future",)
    except ValueError:
        return ContextVerdict.BLOCKED, ("recorded_at invalid",)
    return ContextVerdict.COMPLETE, ()
