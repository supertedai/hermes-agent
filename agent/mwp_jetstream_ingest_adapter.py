"""Bridge Jetstream metadata into the canonical Hermes ingest envelope."""
from __future__ import annotations

from typing import Any

from agent.mwp_ingest_contract import validate_ingest_envelope
from agent.mwp_jetstream_worldmodel_router import JetstreamSignal


def jetstream_to_ingest(signal: JetstreamSignal, *, principal_id: str, tenant_id: str, session_id: str, conversation_id: str, correlation_id: str, observed_at: str) -> dict[str, Any]:
    """Create a metadata-only system observation envelope; never copies raw payload."""
    envelope: dict[str, Any] = {
        "event_id": signal.signal_id,
        "event_type": "jetstream.external_observation",
        "schema_version": "mwp.ingest.v1",
        "runtime_path": "hermes-agent-engine",
        "plane": "system",
        "memory_class": "external-observation",
        "principal_id": principal_id,
        "tenant_id": tenant_id,
        "system_scope": "shared-world-model",
        "session_id": session_id,
        "conversation_id": conversation_id,
        "cortex_ref": "Cortex/world_model_hub",
        "correlation_id": correlation_id,
        "idempotency_key": f"jetstream:{signal.signal_id}",
        "source_ref": signal.source_id,
        "writer_ref": "jetstream-scout",
        "provenance_ref": signal.provenance_ref,
        "observed_at": observed_at,
        "operation": "observe",
        "status": "RECEIVED",
        "payload_ref": signal.payload_ref,
        "gap_refs": list(signal.gap_refs),
        "evidence_refs": list(signal.evidence_refs),
        "injection_checked": signal.injection_checked,
    }
    return envelope


def validate_jetstream_ingest(envelope: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Validate common ingest metadata and Jetstream-specific safety gates."""
    verdict, blockers = validate_ingest_envelope(envelope)
    if blockers:
        return verdict, blockers
    jetstream_blockers: list[str] = []
    if not envelope.get("injection_checked"):
        jetstream_blockers.append("injection scan not verified")
    if not str(envelope.get("payload_ref") or "").strip():
        jetstream_blockers.append("payload reference missing")
    if jetstream_blockers:
        return "QUARANTINED", tuple(jetstream_blockers)
    return verdict, ()
