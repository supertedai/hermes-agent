from agent.mwp_p2_write_preflight import validate_p2_write_preflight


def envelope():
    return {
        "mutation_id": "m1", "idempotency_key": "i1", "operation": "update",
        "canonical_key": "tenant/personal/note/n1", "principal_id": "u1",
        "auth_context_ref": "a1", "canonical_authority_ref": "canon1",
        "source_surface": "desktop", "expected_version": 2,
        "provenance_ref": "p1", "occurred_at": "2026-08-09T00:00:00Z",
        "tenant_id": "t1", "installation_id": "i1", "device_id": "d1",
        "login_surface_id": "ai.byopus.com", "session_id": "s1", "system_scope": "personal",
    }


def canonical():
    return {
        "canonical_key": "tenant/personal/note/n1", "entity_version": 3, "content_hash": "h3",
        "canonical_authority_ref": "canon1", "provenance_ref": "p1",
        "readback_at": "2026-08-09T00:00:01Z", "rollback_ref": "rb1", "freshness_seconds": 10,
    }


def outbox():
    return {"mutation_id": "m1", "canonical_version": 3, "content_hash": "h3", "provenance_ref": "p1", "delivery_state": "DELIVERED", "replay_idempotency": "i1"}


def test_preflight_blocks_without_canonical_evidence():
    result = validate_p2_write_preflight(envelope(), None, None, [])
    assert result["write_allowed"] is False
    assert result["verdict"] == "PENDING_READBACK"


def test_preflight_allows_only_complete_metadata_receipt():
    projection = {"surface_id": "desktop", "projection_state": "FRESH", "entity_version": 3, "content_hash": "h3"}
    result = validate_p2_write_preflight(envelope(), canonical(), outbox(), [projection], required_surfaces=["desktop"])
    assert result["write_allowed"] is True
    assert result["verdict"] == "COMPLETE"


def test_preflight_is_metadata_only():
    result = validate_p2_write_preflight(envelope(), None, None, [])
    assert result["raw_payload_included"] is False
