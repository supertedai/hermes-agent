from agent.mwp_origin_iot_gates import OriginVerdict, metadata_readback, validate_device_origin, validate_iot_steward


def device():
    return {"principal_id":"morten","device_id":"d1","device_class":"desktop","login_surface_id":"s1","transport_origin":"desktop","ssh_hop":"none","authenticated":True}


def iot():
    return {"steward_id":"helios","memory_scope":"shared","writer_ref":"writer-1","read_after_write":True}


def test_complete_origin_and_iot():
    assert validate_device_origin(device()) == (OriginVerdict.COMPLETE, ())
    assert validate_iot_steward(iot()) == (OriginVerdict.COMPLETE, ())


def test_missing_device_chain_is_partial():
    payload=device(); payload.pop("device_id"); payload["authenticated"] = False
    verdict, blockers = validate_device_origin(payload)
    assert verdict == OriginVerdict.PARTIAL
    assert "missing device_id" in blockers


def test_unauthenticated_complete_chain_is_blocked():
    payload=device(); payload["authenticated"] = False
    verdict, blockers = validate_device_origin(payload)
    assert verdict == OriginVerdict.BLOCKED
    assert blockers == ("device origin not authenticated",)


def test_iot_scope_and_writeback_are_required():
    payload=iot(); payload["memory_scope"] = "global"; payload["read_after_write"] = False
    verdict, blockers = validate_iot_steward(payload)
    assert verdict == OriginVerdict.PARTIAL
    assert "invalid IOT memory scope" in blockers
    assert "writer/provisioner read-after-write missing" in blockers


def test_metadata_only_readback():
    result = metadata_readback(device(), iot())
    assert result["device_verdict"] == OriginVerdict.COMPLETE
    assert result["iot_verdict"] == OriginVerdict.COMPLETE
    assert result["raw_payload_included"] is False
