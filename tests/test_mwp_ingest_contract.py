from agent.mwp_ingest_contract import IngestVerdict, metadata_readback, validate_ingest_envelope


def valid():
    return {
        "event_id": "evt-1", "event_type": "chat.turn", "schema_version": "mwp.ingest.v1",
        "runtime_path": "hermes-agent-engine", "plane": "chat", "memory_class": "session",
        "principal_id": "p1", "tenant_id": "t1", "system_scope": "personal", "session_id": "s1",
        "conversation_id": "c1", "correlation_id": "corr-1", "idempotency_key": "idem-1",
        "source_ref": "hermes.session", "provenance_ref": "prov-1", "observed_at": "2026-08-09T12:00:00Z",
        "operation": "observe", "status": "RECEIVED",
    }


def test_valid_chat_envelope():
    assert validate_ingest_envelope(valid()) == (IngestVerdict.VALID, ())


def test_all_four_planes_are_supported():
    for plane in ("chat", "user", "system", "agent"):
        payload = valid() | {"plane": plane}
        assert validate_ingest_envelope(payload)[0] == IngestVerdict.VALID


def test_missing_scope_or_provenance_rejects():
    payload = valid()
    payload.pop("tenant_id")
    payload.pop("provenance_ref")
    verdict, blockers = validate_ingest_envelope(payload)
    assert verdict == IngestVerdict.REJECTED
    assert "missing tenant_id" in blockers
    assert "missing provenance_ref" in blockers


def test_bypass_of_hermes_is_rejected():
    payload = valid() | {"runtime_path": "direct-graph-writer"}
    verdict, blockers = validate_ingest_envelope(payload)
    assert verdict == IngestVerdict.REJECTED
    assert blockers == ("ingest bypasses hermes-agent-engine",)


def test_ambiguous_plane_is_quarantined():
    payload = valid() | {"plane": "unknown"}
    verdict, blockers = validate_ingest_envelope(payload)
    assert verdict == IngestVerdict.QUARANTINED
    assert blockers == ("ambiguous or invalid plane",)


def test_projected_event_requires_canonical_authority():
    payload = valid() | {"status": "PROJECTED"}
    verdict, blockers = validate_ingest_envelope(payload)
    assert verdict == IngestVerdict.QUARANTINED
    assert blockers == ("projected event lacks canonical authority",)


def test_metadata_only_readback():
    result = metadata_readback(valid())
    assert result["verdict"] == IngestVerdict.VALID
    assert result["raw_payload_included"] is False
