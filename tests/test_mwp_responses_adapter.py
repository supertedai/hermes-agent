import pytest

from agent.mwp_responses_adapter import (
    ResponsesAdapterError,
    adapter_receipt,
    normalize_responses_request,
)


BASE = {"model": "gpt-oss-120b", "input": "Reply with OK", "max_output_tokens": 8}


def test_string_input_is_minimal_and_metadata_only_receipt_has_no_raw_payload():
    normalized = normalize_responses_request(BASE)
    assert normalized == BASE
    receipt = adapter_receipt(BASE)
    assert receipt["input_kind"] == "string"
    assert receipt["raw_payload_included"] is False
    assert "Reply" not in str(receipt)


def test_typed_message_drops_openai_metadata_and_preserves_contract():
    payload = {
        "model": "gpt-oss-120b",
        "input": [{
            "id": "msg_private",
            "type": "message",
            "role": "user",
            "status": "completed",
            "content": [{"type": "input_text", "text": "Reply with OK", "annotations": []}],
        }],
        "store": False,
    }
    result = normalize_responses_request(payload)
    assert result["input"] == [{
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reply with OK"}]
    }]
    assert "id" not in result["input"][0]
    assert "store" not in result


def test_unknown_item_type_fails_closed():
    payload = {"model": "gpt-oss-120b", "input": [{"type": "unknown", "content": []}]}
    with pytest.raises(ResponsesAdapterError, match="unsupported Responses input item type"):
        normalize_responses_request(payload)


def test_incomplete_reasoning_item_fails_closed_instead_of_reaching_runtime():
    payload = {"model": "gpt-oss-120b", "input": [{"type": "reasoning", "summary": []}]}
    with pytest.raises(ResponsesAdapterError, match="unsupported Responses input item type"):
        normalize_responses_request(payload)


def test_function_call_round_trip_is_restricted_to_safe_fields():
    payload = {
        "model": "gpt-oss-120b",
        "input": [
            {"type": "function_call", "call_id": "call_1", "name": "inspect", "arguments": "{}", "id": "private"},
            {"type": "function_call_output", "call_id": "call_1", "output": "ok", "status": "completed"},
        ],
    }
    result = normalize_responses_request(payload)
    assert result["input"] == [
        {"type": "function_call", "call_id": "call_1", "name": "inspect", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "ok"},
    ]
