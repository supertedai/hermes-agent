from agent.mwp_identity_projection import IdentityVerdict, metadata_readback, validate_identity_readback


def valid():
    return {
        "user_id": "morten",
        "principal_id": "morten",
        "conversation_id": "conv-1",
        "client_session_id": "client-1",
        "durable_session_id": "durable-1",
        "device_id": "device-1",
        "device_class": "desktop",
        "transport_origin": "hermes-desktop",
        "ssh_hop": "none",
        "provenance": ["desktop.auth", "gateway.session"],
    }


def test_complete_identity_chain():
    verdict, blockers = validate_identity_readback(valid())
    assert verdict == IdentityVerdict.COMPLETE
    assert blockers == ()


def test_missing_session_or_device_blocks():
    payload = valid()
    payload.pop("durable_session_id")
    payload.pop("device_id")
    verdict, blockers = validate_identity_readback(payload)
    assert verdict == IdentityVerdict.BLOCKED
    assert "missing durable_session_id" in blockers
    assert "missing device_id" in blockers


def test_principal_mismatch_blocks():
    payload = valid()
    payload["principal_id"] = "other"
    verdict, blockers = validate_identity_readback(payload)
    assert verdict == IdentityVerdict.BLOCKED
    assert blockers == ("principal_id does not match user_id",)


def test_missing_transport_provenance_is_unverified():
    payload = valid()
    payload.pop("ssh_hop")
    verdict, blockers = validate_identity_readback(payload)
    assert verdict == IdentityVerdict.UNVERIFIED
    assert blockers == ("ssh_hop provenance not recorded",)


def test_readback_is_metadata_only():
    output = metadata_readback(valid())
    assert output["verdict"] == IdentityVerdict.COMPLETE
    assert output["raw_payload_included"] is False
