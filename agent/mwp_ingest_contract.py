"""Fail-closed metadata validation for the four-plane MWP ingest envelope."""
from __future__ import annotations

from typing import Any, Mapping


class IngestVerdict(str):
    VALID = "VALID"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


REQUIRED = (
    "event_id", "event_type", "schema_version", "runtime_path", "plane",
    "memory_class", "principal_id", "tenant_id", "system_scope", "session_id",
    "conversation_id", "correlation_id", "idempotency_key", "source_ref",
    "provenance_ref", "observed_at", "operation", "status",
)
PLANES = {"chat", "user", "system", "agent"}
OPERATIONS = {"observe", "candidate", "promote", "correct", "tombstone", "handoff", "outcome"}
STATUSES = {"RECEIVED", "VALIDATED", "QUARANTINED", "REJECTED", "ROUTED", "PROJECTED"}


def validate_ingest_envelope(envelope: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Validate routing metadata only; payload content is intentionally ignored."""
    missing = tuple(key for key in REQUIRED if not str(envelope.get(key) or "").strip())
    if missing:
        return IngestVerdict.REJECTED, tuple(f"missing {key}" for key in missing)
    if envelope.get("schema_version") != "mwp.ingest.v1":
        return IngestVerdict.REJECTED, ("unsupported schema_version",)
    if envelope.get("runtime_path") != "hermes-agent-engine":
        return IngestVerdict.REJECTED, ("ingest bypasses hermes-agent-engine",)
    if envelope.get("plane") not in PLANES:
        return IngestVerdict.QUARANTINED, ("ambiguous or invalid plane",)
    if envelope.get("operation") not in OPERATIONS:
        return IngestVerdict.REJECTED, ("invalid operation",)
    if envelope.get("status") not in STATUSES:
        return IngestVerdict.REJECTED, ("invalid status",)
    if envelope.get("status") == "PROJECTED" and not str(envelope.get("canonical_authority_ref") or "").strip():
        return IngestVerdict.QUARANTINED, ("projected event lacks canonical authority",)
    return IngestVerdict.VALID, ()


def metadata_readback(envelope: Mapping[str, Any]) -> dict[str, Any]:
    verdict, blockers = validate_ingest_envelope(envelope)
    return {
        "verdict": verdict,
        "blockers": list(blockers),
        "runtime_path": envelope.get("runtime_path"),
        "plane": envelope.get("plane"),
        "raw_payload_included": False,
    }
