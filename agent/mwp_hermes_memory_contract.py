"""Fail-closed metadata contract for Hermes-centred memory routing."""
from __future__ import annotations

from typing import Any, Mapping


class HermesMemoryVerdict(str):
    COMPLETE = "COMPLETE"
    UNVERIFIED = "UNVERIFIED"
    BLOCKED = "BLOCKED"


_REQUIRED = (
    "receipt_id", "principal_id", "tenant_id", "system_scope",
    "conversation_id", "session_id", "memory_layer_id", "provenance_ref",
)


def validate_hermes_memory_receipt(receipt: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Validate routing metadata only; never accepts or returns memory payloads."""
    missing = tuple(key for key in _REQUIRED if not str(receipt.get(key) or "").strip())
    if missing:
        return HermesMemoryVerdict.BLOCKED, tuple(f"missing {key}" for key in missing)
    if receipt.get("runtime_path") != "hermes-agent-engine":
        return HermesMemoryVerdict.BLOCKED, ("hermes engine is not recorded as runtime path",)
    if receipt.get("projection_state") not in {"FRESH", "STALE", "DIVERGED", "UNKNOWN"}:
        return HermesMemoryVerdict.UNVERIFIED, ("projection state missing or invalid",)
    if not str(receipt.get("status") or "").strip():
        return HermesMemoryVerdict.BLOCKED, ("status missing",)
    if receipt.get("status") not in {"READ", "WRITE_ACCEPTED", "WRITE_CONFIRMED", "QUARANTINED", "READ_ONLY"}:
        return HermesMemoryVerdict.UNVERIFIED, ("memory receipt status is not recognized",)
    if receipt.get("status") == "WRITE_CONFIRMED":
        for key in ("canonical_authority_ref", "entity_version", "content_hash", "rollback_ref"):
            if not str(receipt.get(key) or "").strip():
                return HermesMemoryVerdict.BLOCKED, (f"missing {key} for confirmed write",)
        if receipt.get("read_after_write") is not True:
            return HermesMemoryVerdict.BLOCKED, ("confirmed write lacks read-after-write",)
    if receipt.get("runtime_effective") is not True:
        return HermesMemoryVerdict.UNVERIFIED, ("runtime effect not verified",)
    return HermesMemoryVerdict.COMPLETE, ()


def metadata_readback(receipt: Mapping[str, Any]) -> dict[str, Any]:
    verdict, blockers = validate_hermes_memory_receipt(receipt)
    return {
        "verdict": verdict,
        "blockers": list(blockers),
        "runtime_path": receipt.get("runtime_path"),
        "raw_payload_included": False,
    }
