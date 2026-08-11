from agent.mwp_hermes_memory_contract import HermesMemoryVerdict, metadata_readback, validate_hermes_memory_receipt


def valid():
    return {
        "receipt_id": "rcpt-1",
        "principal_id": "principal-1",
        "tenant_id": "tenant-1",
        "system_scope": "personal",
        "conversation_id": "conv-1",
        "session_id": "sess-1",
        "memory_layer_id": "chat-extracted-facts",
        "provenance_ref": "prov-1",
        "runtime_path": "hermes-agent-engine",
        "projection_state": "FRESH",
        "status": "READ",
        "runtime_effective": True,
    }


def test_hermes_engine_is_required_runtime_path():
    payload = valid()
    payload["runtime_path"] = "direct-graph"
    verdict, blockers = validate_hermes_memory_receipt(payload)
    assert verdict == HermesMemoryVerdict.BLOCKED
    assert blockers == ("hermes engine is not recorded as runtime path",)


def test_scope_and_provenance_are_required():
    payload = valid()
    payload.pop("tenant_id")
    payload.pop("provenance_ref")
    verdict, blockers = validate_hermes_memory_receipt(payload)
    assert verdict == HermesMemoryVerdict.BLOCKED
    assert "missing tenant_id" in blockers
    assert "missing provenance_ref" in blockers


def test_confirmed_write_requires_read_after_write_and_rollback():
    payload = valid() | {"status": "WRITE_CONFIRMED", "canonical_authority_ref": "fabric", "entity_version": 1, "content_hash": "hash"}
    verdict, blockers = validate_hermes_memory_receipt(payload)
    assert verdict == HermesMemoryVerdict.BLOCKED
    assert "missing rollback_ref for confirmed write" in blockers


def test_runtime_effect_is_required_for_complete():
    payload = valid()
    payload["runtime_effective"] = False
    verdict, blockers = validate_hermes_memory_receipt(payload)
    assert verdict == HermesMemoryVerdict.UNVERIFIED
    assert blockers == ("runtime effect not verified",)


def test_metadata_only_readback():
    result = metadata_readback(valid())
    assert result["verdict"] == HermesMemoryVerdict.COMPLETE
    assert result["raw_payload_included"] is False
