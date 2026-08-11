"""Minimal W3C Trace Context helper for MWP boundaries."""
from __future__ import annotations

import re
import secrets

_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def new_traceparent(*, sampled: bool = True) -> str:
    """Create a valid W3C traceparent value without carrying payload data."""
    trace_id = secrets.token_hex(16)
    parent_id = secrets.token_hex(8)
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{parent_id}-{flags}"


def validate_traceparent(value: str) -> bool:
    """Validate format only; this does not prove a trace exists."""
    if not _TRACEPARENT.fullmatch(value):
        return False
    trace_id = value.split("-")[1]
    parent_id = value.split("-")[2]
    return trace_id != "0" * 32 and parent_id != "0" * 16
