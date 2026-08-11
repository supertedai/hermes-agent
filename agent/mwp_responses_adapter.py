"""Fail-closed Responses payload adapter for the BL-3923 llama.cpp gate.

This module is deliberately standalone: it does not activate Halo, call a model,
or mutate a repository. It makes the compatibility boundary testable before any
runtime integration is considered.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class ResponsesAdapterError(ValueError):
    """Raised when a payload cannot be proven compatible with llama.cpp."""


def _content_parts(role: str, content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "input_text" if role == "user" else "output_text", "text": content}]
    if not isinstance(content, list):
        raise ResponsesAdapterError("message content must be a string or array")
    result: list[dict[str, Any]] = []
    accepted = {"input_text", "output_text"}
    for part in content:
        if not isinstance(part, Mapping) or part.get("type") not in accepted:
            raise ResponsesAdapterError("message content contains an unsupported item type")
        text = part.get("text")
        if not isinstance(text, str):
            raise ResponsesAdapterError("message content text must be a string")
        result.append({"type": part["type"], "text": text})
    if not result:
        raise ResponsesAdapterError("message content must not be empty")
    return result


def _normalize_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ResponsesAdapterError("input item must be an object")
    item_type = item.get("type")
    if item_type == "message":
        role = item.get("role")
        if role not in {"user", "assistant", "system"}:
            raise ResponsesAdapterError("message role is required and must be supported")
        return {"type": "message", "role": role, "content": _content_parts(role, item.get("content"))}
    if item_type == "function_call":
        required = ("call_id", "name", "arguments")
        if any(not isinstance(item.get(key), str) or not item[key] for key in required):
            raise ResponsesAdapterError("function_call requires non-empty call_id, name and arguments")
        return {key: item[key] for key in ("type", "call_id", "name", "arguments")}
    if item_type == "function_call_output":
        if not isinstance(item.get("call_id"), str) or not item["call_id"]:
            raise ResponsesAdapterError("function_call_output requires call_id")
        output = item.get("output")
        if not isinstance(output, str):
            raise ResponsesAdapterError("function_call_output requires string output")
        return {"type": "function_call_output", "call_id": item["call_id"], "output": output}
    raise ResponsesAdapterError(f"unsupported Responses input item type: {item_type!r}")


def normalize_responses_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the smallest known-compatible llama.cpp Responses request.

    Unknown top-level fields are rejected rather than silently forwarded. This
    prevents an OpenAI-only option or malformed trace item from becoming a
    runtime 400 inside Halo.
    """
    if not isinstance(payload, Mapping):
        raise ResponsesAdapterError("request must be an object")
    allowed = {
        "model", "input", "instructions", "max_output_tokens", "temperature", "top_p",
        "tools", "tool_choice", "parallel_tool_calls", "reasoning",
    }
    # OpenAI bookkeeping/options known to be harmless but not part of the
    # llama.cpp compatibility surface. They are intentionally stripped.
    strip_known = {"include", "store", "background"}
    unknown = sorted(set(payload) - allowed - strip_known)
    if unknown:
        raise ResponsesAdapterError("unsupported top-level fields: " + ", ".join(unknown))
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ResponsesAdapterError("model is required")
    input_value = payload.get("input")
    if isinstance(input_value, str):
        normalized_input: str | list[dict[str, Any]] = input_value
    elif isinstance(input_value, list):
        normalized_input = [_normalize_item(item) for item in deepcopy(input_value)]
        if not normalized_input:
            raise ResponsesAdapterError("input array must not be empty")
    else:
        raise ResponsesAdapterError("input must be a string or non-empty array")
    result: dict[str, Any] = {"model": model, "input": normalized_input}
    for key in allowed - {"model", "input"}:
        if key in payload:
            result[key] = deepcopy(payload[key])
    return result


def adapter_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Metadata-only validation receipt; never includes raw prompt content."""
    normalized = normalize_responses_request(payload)
    input_value = normalized["input"]
    item_count = len(input_value) if isinstance(input_value, list) else 1
    return {
        "adapter": "mwp-responses-llamacpp-v1",
        "verified": False,
        "model_present": bool(normalized["model"]),
        "input_kind": "array" if isinstance(input_value, list) else "string",
        "input_item_count": item_count,
        "raw_payload_included": False,
    }
