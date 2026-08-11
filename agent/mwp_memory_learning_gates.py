"""Fail-closed metadata gates for memory retrieval and learning promotion."""
from __future__ import annotations

from typing import Any, Mapping


class MemoryVerdict(str):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


def validate_memory_learning(readback: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    blockers: list[str] = []
    for key in ("retrieval_id", "scope", "provenance_ref"):
        if not str(readback.get(key) or "").strip():
            blockers.append(f"missing {key}")
    if readback.get("scope") not in {"private", "shared", "agent", "system"}:
        blockers.append("invalid memory scope")
    if readback.get("used") is not True:
        blockers.append("retrieved insight use not read back")
    if readback.get("effect_measured") is not True:
        blockers.append("effect measurement missing")
    if readback.get("learning_signal") is not True:
        blockers.append("learning signal missing")
    if blockers:
        if "promotion gate not closed" not in blockers:
            blockers.append("promotion gate not closed")
        return MemoryVerdict.PARTIAL, tuple(blockers)
    if readback.get("promotion_approved") is True and readback.get("promotion_receipt"):
        return MemoryVerdict.COMPLETE, ()
    return MemoryVerdict.BLOCKED, ("promotion gate not closed",)


def metadata_readback(readback: Mapping[str, Any]) -> dict[str, Any]:
    verdict, blockers = validate_memory_learning(readback)
    return {
        "verdict": verdict,
        "blockers": list(blockers),
        "raw_payload_included": False,
    }
