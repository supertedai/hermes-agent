"""Metadata-only conformance checks for the governed MWP data plane."""
from __future__ import annotations

from typing import Any, Mapping


class DataPlaneVerdict(str):
    COMPLETE = "COMPLETE"
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"


def validate_data_plane_readback(readback: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    blockers: list[str] = []
    for key in ("schema_id", "schema_version", "canonical_authority_ref", "scope", "provenance_ref"):
        if not str(readback.get(key) or "").strip():
            blockers.append(f"missing {key}")
    if readback.get("projection_state") not in {"FRESH", "STALE", "DIVERGED", "UNKNOWN"}:
        blockers.append("invalid projection_state")
    if readback.get("derived_only") is not True:
        blockers.append("derived store is not labelled derived_only")
    if readback.get("read_after_write") is not True:
        blockers.append("read-after-write missing")
    if readback.get("rollback_ref") in (None, ""):
        blockers.append("rollback_ref missing")
    if blockers:
        return DataPlaneVerdict.BLOCKED, tuple(blockers)
    if readback.get("quality_baseline") is not True:
        return DataPlaneVerdict.OPEN, ("quality baseline missing",)
    return DataPlaneVerdict.COMPLETE, ()


def validate_vector_collection_descriptor(descriptor: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    required = (
        "collection_id", "schema_id", "schema_version", "owner",
        "embedding_model_ref", "dimension", "distance_metric",
        "point_identity", "scope_policy", "payload_indexes",
    )
    missing = tuple(key for key in required if not descriptor.get(key) and descriptor.get(key) != 0)
    if missing:
        return DataPlaneVerdict.BLOCKED, tuple(f"missing vector:{key}" for key in missing)
    dimension = descriptor.get("dimension")
    if not isinstance(dimension, int) or dimension <= 0:
        return DataPlaneVerdict.BLOCKED, ("invalid vector:dimension",)
    if descriptor.get("derived_only") is not True:
        return DataPlaneVerdict.BLOCKED, ("vector store must be labelled derived_only",)
    return DataPlaneVerdict.COMPLETE, ()


def validate_gnn_model_descriptor(descriptor: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    required = (
        "model_id", "model_version", "checkpoint_hash", "feature_schema",
        "label_schema", "evaluation_baseline", "serving_route", "rollback_ref",
    )
    missing = tuple(key for key in required if not descriptor.get(key))
    if missing:
        return DataPlaneVerdict.BLOCKED, tuple(f"missing gnn:{key}" for key in missing)
    if descriptor.get("derived_only") is not True:
        return DataPlaneVerdict.BLOCKED, ("gnn output must be labelled derived_only",)
    if descriptor.get("leakage_controls") is not True:
        return DataPlaneVerdict.OPEN, ("gnn leakage controls missing",)
    return DataPlaneVerdict.COMPLETE, ()


def metadata_readback(readback: Mapping[str, Any]) -> dict[str, Any]:
    verdict, blockers = validate_data_plane_readback(readback)
    return {"verdict": verdict, "blockers": list(blockers), "raw_payload_included": False}
