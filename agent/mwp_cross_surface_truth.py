"""Fail-closed cross-surface truth gates for CRUD mutation receipts."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


class TruthVerdict(str):
    COMPLETE = "COMPLETE"
    PENDING_READBACK = "PENDING_READBACK"
    STALE = "STALE"
    BLOCKED = "BLOCKED"
    DIVERGED = "DIVERGED"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


_REQUIRED_ENVELOPE = (
    "mutation_id", "idempotency_key", "operation", "canonical_key",
    "principal_id", "auth_context_ref", "canonical_authority_ref",
    "source_surface", "provenance_ref", "occurred_at",
)

_STRICT_TOPOLOGY_FIELDS = (
    "tenant_id", "installation_id", "device_id", "login_surface_id",
    "session_id", "system_scope",
)


def validate_mutation_envelope(envelope: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    missing = tuple(k for k in _REQUIRED_ENVELOPE if not envelope.get(k))
    if missing:
        return TruthVerdict.BLOCKED, tuple(f"missing:{k}" for k in missing)
    if envelope.get("operation") not in {"create", "read", "update", "delete"}:
        return TruthVerdict.BLOCKED, ("invalid:operation",)
    if envelope.get("operation") == "update" and envelope.get("expected_version") is None:
        return TruthVerdict.CONFLICT, ("missing:expected_version",)
    return TruthVerdict.COMPLETE, ()


def validate_strict_mutation_envelope(envelope: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Require full topology scope before a CRUD event can enter P2."""
    verdict, blockers = validate_mutation_envelope(envelope)
    if verdict != TruthVerdict.COMPLETE:
        return verdict, blockers
    missing = tuple(key for key in _STRICT_TOPOLOGY_FIELDS if not envelope.get(key))
    if missing:
        return TruthVerdict.BLOCKED, tuple(f"missing:{key}" for key in missing)
    return TruthVerdict.COMPLETE, ()


def validate_truth_receipts(
    envelope: Mapping[str, Any],
    canonical: Mapping[str, Any] | None,
    outbox: Mapping[str, Any] | None,
    projections: Sequence[Mapping[str, Any]],
    *,
    required_surfaces: Sequence[str] = (),
) -> tuple[str, tuple[str, ...]]:
    verdict, blockers = validate_mutation_envelope(envelope)
    if verdict != TruthVerdict.COMPLETE:
        return verdict, blockers
    if not canonical:
        return TruthVerdict.PENDING_READBACK, ("missing:canonical_read_after_write",)
    if canonical.get("canonical_key") != envelope.get("canonical_key"):
        return TruthVerdict.DIVERGED, ("canonical_key:mismatch",)
    if not canonical.get("entity_version") or not canonical.get("content_hash"):
        return TruthVerdict.PENDING_READBACK, ("canonical:version_or_hash_missing",)
    if not outbox or outbox.get("mutation_id") != envelope.get("mutation_id"):
        return TruthVerdict.BLOCKED, ("outbox:missing_or_mismatched",)
    if outbox.get("canonical_version") != canonical.get("entity_version"):
        return TruthVerdict.DIVERGED, ("outbox:version_mismatch",)
    by_surface = {str(p.get("surface_id")): p for p in projections}
    for surface in required_surfaces:
        p = by_surface.get(surface)
        if not p:
            return TruthVerdict.PENDING_READBACK, (f"projection:missing:{surface}",)
        if p.get("projection_state") != "FRESH":
            return TruthVerdict.STALE, (f"projection:not_fresh:{surface}",)
        if p.get("entity_version") != canonical.get("entity_version"):
            return TruthVerdict.DIVERGED, (f"projection:version_mismatch:{surface}",)
        if p.get("content_hash") != canonical.get("content_hash"):
            return TruthVerdict.DIVERGED, (f"projection:hash_mismatch:{surface}",)
    return TruthVerdict.COMPLETE, ()


def validate_strict_truth_receipts(
    envelope: Mapping[str, Any],
    canonical: Mapping[str, Any] | None,
    outbox: Mapping[str, Any] | None,
    projections: Sequence[Mapping[str, Any]],
    *,
    required_surfaces: Sequence[str] = (),
) -> tuple[str, tuple[str, ...]]:
    """Require full P2 authority, provenance, freshness, rollback and outbox evidence."""
    verdict, blockers = validate_strict_mutation_envelope(envelope)
    if verdict != TruthVerdict.COMPLETE:
        return verdict, blockers
    if not canonical:
        return TruthVerdict.PENDING_READBACK, ("missing:canonical_read_after_write",)
    required_canonical = (
        "canonical_authority_ref", "canonical_key", "entity_version", "content_hash",
        "provenance_ref", "readback_at", "rollback_ref", "freshness_seconds",
    )
    missing_canonical = tuple(key for key in required_canonical if not canonical.get(key) and canonical.get(key) != 0)
    if missing_canonical:
        return TruthVerdict.PENDING_READBACK, tuple(f"canonical:missing:{key}" for key in missing_canonical)
    if canonical.get("canonical_authority_ref") != envelope.get("canonical_authority_ref"):
        return TruthVerdict.BLOCKED, ("canonical:authority_mismatch",)
    freshness = canonical.get("freshness_seconds")
    if not isinstance(freshness, int) or freshness < 0:
        return TruthVerdict.STALE, ("canonical:freshness_invalid",)
    if not outbox or outbox.get("mutation_id") != envelope.get("mutation_id"):
        return TruthVerdict.BLOCKED, ("outbox:missing_or_mismatched",)
    required_outbox = ("canonical_version", "content_hash", "provenance_ref", "delivery_state", "replay_idempotency")
    missing_outbox = tuple(key for key in required_outbox if not outbox.get(key))
    if missing_outbox:
        return TruthVerdict.BLOCKED, tuple(f"outbox:missing:{key}" for key in missing_outbox)
    if outbox.get("canonical_version") != canonical.get("entity_version"):
        return TruthVerdict.DIVERGED, ("outbox:version_mismatch",)
    if outbox.get("content_hash") != canonical.get("content_hash"):
        return TruthVerdict.DIVERGED, ("outbox:hash_mismatch",)
    return validate_truth_receipts(envelope, canonical, outbox, projections, required_surfaces=required_surfaces)


def metadata_readback(verdict: str, blockers: Sequence[str]) -> dict[str, Any]:
    return {"verdict": verdict, "blockers": list(blockers), "raw_payload_included": False}
