from datetime import datetime, timezone

from agent.mwp_context_projection import ContextVerdict, validate_context_readback


NOW = datetime(2026, 8, 6, 13, 40, tzinfo=timezone.utc)


def valid():
    return {
        "conversation_id": "conv-1",
        "user_id": "user-1",
        "working_model_ref": "wm-1",
        "cortex_ref": "cx-1",
        "agent_id": "agent-1",
        "agent_role": "reasoner",
        "agent_binding_ref": "binding-1",
        "handoff_ref": "handoff-1",
        "recorded_at": "2026-08-06T13:39:00Z",
        "freshness_seconds": 60,
        "provenance": ["chat.gateway", "cortex.readback"],
    }


def test_complete_metadata_only_context_readback():
    verdict, blockers = validate_context_readback(valid(), now=NOW)
    assert verdict == ContextVerdict.COMPLETE
    assert blockers == ()


def test_missing_identity_or_model_refs_block():
    payload = valid()
    payload.pop("user_id")
    payload.pop("working_model_ref")
    payload.pop("agent_binding_ref")
    verdict, blockers = validate_context_readback(payload, now=NOW)
    assert verdict == ContextVerdict.BLOCKED
    assert "missing user_id" in blockers
    assert "missing working_model_ref" in blockers
    assert "missing agent_binding_ref" in blockers


def test_stale_or_invalid_freshness_is_unverified():
    payload = valid()
    payload["freshness_seconds"] = 901
    verdict, blockers = validate_context_readback(payload, now=NOW)
    assert verdict == ContextVerdict.UNVERIFIED
    assert blockers == ("context readback stale",)


def test_bad_provenance_and_future_timestamp_block_or_unverify():
    payload = valid()
    payload["provenance"] = []
    verdict, blockers = validate_context_readback(payload, now=NOW)
    assert verdict == ContextVerdict.BLOCKED
    assert blockers == ("provenance missing or invalid",)

    payload = valid()
    payload["recorded_at"] = "2026-08-06T13:41:00Z"
    verdict, blockers = validate_context_readback(payload, now=NOW)
    assert verdict == ContextVerdict.UNVERIFIED
    assert blockers == ("recorded_at is in the future",)
