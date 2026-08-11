from agent.mwp_memory_learning_gates import MemoryVerdict, metadata_readback, validate_memory_learning


def valid():
    return {
        "retrieval_id": "ret-1",
        "scope": "shared",
        "provenance_ref": "prov-1",
        "used": True,
        "effect_measured": True,
        "learning_signal": True,
        "promotion_approved": True,
        "promotion_receipt": "promo-1",
    }


def test_complete_requires_promotion_receipt():
    verdict, blockers = validate_memory_learning(valid())
    assert verdict == MemoryVerdict.COMPLETE
    assert blockers == ()


def test_retrieval_without_use_and_effect_is_partial():
    payload = valid()
    payload["used"] = False
    payload["effect_measured"] = False
    payload["promotion_approved"] = False
    verdict, blockers = validate_memory_learning(payload)
    assert verdict == MemoryVerdict.PARTIAL
    assert "retrieved insight use not read back" in blockers
    assert "effect measurement missing" in blockers
    assert "promotion gate not closed" in blockers


def test_invalid_scope_blocks_progress():
    payload = valid()
    payload["scope"] = "global"
    verdict, blockers = validate_memory_learning(payload)
    assert verdict == MemoryVerdict.PARTIAL
    assert "invalid memory scope" in blockers


def test_readback_is_metadata_only():
    result = metadata_readback(valid())
    assert result["verdict"] == MemoryVerdict.COMPLETE
    assert result["raw_payload_included"] is False
