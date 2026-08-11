"""Fail-closed validators for shared-world-model rollback and retrieval quality."""
from __future__ import annotations

from typing import Any, Mapping


class WorldModelVerdict(str):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


def validate_rollback_handles(targets: Mapping[str, Mapping[str, Any]]) -> tuple[str, tuple[str, ...]]:
    blockers: list[str] = []
    for target in ("graph", "qdrant", "gnn"):
        item = targets.get(target) or {}
        if item.get("service_reachable") is not True:
            blockers.append(f"{target} service not reachable")
        if not str(item.get("snapshot_handle") or item.get("checkpoint_handle") or "").strip():
            blockers.append(f"{target} snapshot/checkpoint handle missing")
        if not str(item.get("rollback_ref") or "").strip():
            blockers.append(f"{target} rollback_ref missing")
    if blockers:
        return WorldModelVerdict.BLOCKED, tuple(blockers)
    return WorldModelVerdict.COMPLETE, ()


def validate_retrieval_quality(readback: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    blockers: list[str] = []
    if readback.get("stable_chunk_identity") is not True:
        blockers.append("stable chunk identity missing")
    if readback.get("owner_labels") is not True:
        blockers.append("owner labels missing")
    if not isinstance(readback.get("precision_at_k"), (int, float)):
        blockers.append("precision_at_k unverified")
    if not isinstance(readback.get("recall_at_k"), (int, float)):
        blockers.append("recall_at_k unverified")
    if readback.get("gnn_degraded") is True:
        blockers.append("GNN degraded")
    if blockers:
        return WorldModelVerdict.PARTIAL, tuple(blockers)
    return WorldModelVerdict.COMPLETE, ()


def metadata_readback(targets: Mapping[str, Mapping[str, Any]], retrieval: Mapping[str, Any]) -> dict[str, Any]:
    rollback_verdict, rollback_blockers = validate_rollback_handles(targets)
    quality_verdict, quality_blockers = validate_retrieval_quality(retrieval)
    return {
        "rollback_verdict": rollback_verdict,
        "rollback_blockers": list(rollback_blockers),
        "quality_verdict": quality_verdict,
        "quality_blockers": list(quality_blockers),
        "raw_payload_included": False,
    }
