"""Metadata-only adapter for Hermes MemoryManager lifecycle events."""
from __future__ import annotations

import hashlib
from typing import Any, Mapping


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def memory_lifecycle_envelope(
    *,
    event_type: str,
    provider_name: str,
    principal_id: str,
    tenant_id: str,
    system_scope: str,
    session_id: str,
    conversation_id: str,
    correlation_id: str,
    observed_at: str,
    source_ref: str = "hermes.memory_manager",
) -> dict[str, Any]:
    """Build an ingest envelope without including memory or chat payload."""
    if not all(str(v).strip() for v in (event_type, provider_name, principal_id, tenant_id, system_scope, session_id, conversation_id, correlation_id, observed_at)):
        raise ValueError("lifecycle receipt requires event/provider/scope/session/correlation metadata")
    operation = "observe" if event_type in {"prefetch", "queue_prefetch"} else "outcome"
    return {
        "event_id": "mem-" + _id(event_type, provider_name, correlation_id, observed_at),
        "event_type": event_type,
        "schema_version": "mwp.ingest.v1",
        "runtime_path": "hermes-agent-engine",
        "plane": "chat" if event_type in {"prefetch", "queue_prefetch", "sync_turn"} else "system",
        "memory_class": "provider-lifecycle-metadata",
        "principal_id": principal_id,
        "tenant_id": tenant_id,
        "system_scope": system_scope,
        "session_id": session_id,
        "conversation_id": conversation_id,
        "correlation_id": correlation_id,
        "idempotency_key": "mem-" + _id(provider_name, event_type, correlation_id),
        "source_ref": source_ref,
        "provenance_ref": f"hermes-memory-manager:{provider_name}",
        "observed_at": observed_at,
        "operation": operation,
        "status": "RECEIVED",
        "provider_name": provider_name,
        "payload_included": False,
    }
