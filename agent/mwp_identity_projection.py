"""Fail-closed metadata validator for the MWP remote identity chain."""
from __future__ import annotations

from typing import Any, Mapping


class IdentityVerdict(str):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


REQUIRED_IDENTITY_FIELDS = (
    "user_id",
    "conversation_id",
    "client_session_id",
    "durable_session_id",
    "device_id",
    "device_class",
    "transport_origin",
    "principal_id",
)


def validate_identity_readback(readback: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Validate identity lineage without exposing or mutating identity payloads."""
    missing = tuple(
        key for key in REQUIRED_IDENTITY_FIELDS
        if not str(readback.get(key) or "").strip()
    )
    if missing:
        return IdentityVerdict.BLOCKED, tuple(f"missing {key}" for key in missing)
    if readback.get("principal_id") != readback.get("user_id"):
        return IdentityVerdict.BLOCKED, ("principal_id does not match user_id",)
    provenance = readback.get("provenance")
    if not isinstance(provenance, list) or not provenance:
        return IdentityVerdict.UNVERIFIED, ("identity provenance missing",)
    if readback.get("ssh_hop") is None:
        return IdentityVerdict.UNVERIFIED, ("ssh_hop provenance not recorded",)
    return IdentityVerdict.COMPLETE, ()


def metadata_readback(readback: Mapping[str, Any]) -> dict[str, Any]:
    verdict, blockers = validate_identity_readback(readback)
    return {
        "verdict": verdict,
        "blockers": list(blockers),
        "required_fields": list(REQUIRED_IDENTITY_FIELDS),
        "raw_payload_included": False,
    }
