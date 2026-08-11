"""Fail-closed metadata gates for device origin and IOT steward bindings."""
from __future__ import annotations

from typing import Any, Mapping


class OriginVerdict(str):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


def validate_device_origin(readback: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    required = ("principal_id", "device_id", "device_class", "login_surface_id", "transport_origin")
    blockers = [f"missing {key}" for key in required if not str(readback.get(key) or "").strip()]
    if readback.get("ssh_hop") is None:
        blockers.append("ssh_hop provenance missing")
    if not isinstance(readback.get("authenticated"), bool):
        blockers.append("authenticated flag missing")
    if blockers:
        return OriginVerdict.PARTIAL, tuple(blockers)
    if readback.get("authenticated") is not True:
        return OriginVerdict.BLOCKED, ("device origin not authenticated",)
    return OriginVerdict.COMPLETE, ()


def validate_iot_steward(readback: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    required = ("steward_id", "memory_scope", "writer_ref")
    blockers = [f"missing {key}" for key in required if not str(readback.get(key) or "").strip()]
    if readback.get("memory_scope") not in {"private", "shared", "agent", "system"}:
        blockers.append("invalid IOT memory scope")
    if readback.get("read_after_write") is not True:
        blockers.append("writer/provisioner read-after-write missing")
    if blockers:
        return OriginVerdict.PARTIAL, tuple(blockers)
    return OriginVerdict.COMPLETE, ()


def metadata_readback(device: Mapping[str, Any], iot: Mapping[str, Any]) -> dict[str, Any]:
    device_verdict, device_blockers = validate_device_origin(device)
    iot_verdict, iot_blockers = validate_iot_steward(iot)
    return {
        "device_verdict": device_verdict,
        "device_blockers": list(device_blockers),
        "iot_verdict": iot_verdict,
        "iot_blockers": list(iot_blockers),
        "raw_payload_included": False,
    }
