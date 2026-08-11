"""Fail-closed change ledger for MWP CAD/ADR/BL/graph/Obsidian alignment.

The ledger is metadata-only. It creates provisional identifiers for every
material change, but never pretends that a git commit, graph write, or Obsidian
write happened without a receipt from that destination.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class ChangeStatus(str, Enum):
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class DestinationReceipt:
    destination: str
    status: str
    ref: str
    verified_at: str


@dataclass(frozen=True)
class ChangeEvent:
    event_id: str
    cad_id: str
    adr_id: str
    bl_id: str
    provisional: bool
    principal: str
    installation_id: str
    login_surface_id: str
    agent_id: str
    system_scope: str
    action: str
    intent: str
    evidence_refs: tuple[str, ...]
    receipts: tuple[DestinationReceipt, ...]
    status: ChangeStatus
    created_at: str
    gap: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


def _timestamp() -> str:
    now = time.time_ns()
    whole = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now // 1_000_000_000))
    return f"{whole}.{now % 1_000_000_000:09d}Z"


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def provisional_ids(*, action: str, intent: str, principal: str, installation_id: str) -> tuple[str, str, str]:
    token = _digest(action, intent, principal, installation_id, _timestamp())
    return f"CAD-EVT-{token}", f"ADR-EVT-{token}", f"BL-EVT-{token}"


def _status(receipts: Iterable[DestinationReceipt]) -> tuple[ChangeStatus, str]:
    by_destination = {r.destination: r for r in receipts}
    required = {"git", "graph", "obsidian"}
    missing = sorted(required - set(by_destination))
    bad = sorted(d for d in required if d in by_destination and by_destination[d].status != "VERIFIED")
    if missing:
        return ChangeStatus.OPEN, "missing receipts: " + ", ".join(missing)
    if bad:
        return ChangeStatus.BLOCKED, "unverified receipts: " + ", ".join(bad)
    return ChangeStatus.COMPLETE, "all destination receipts verified"


def record_change(
    *,
    action: str,
    intent: str,
    principal: str,
    installation_id: str,
    login_surface_id: str,
    agent_id: str,
    system_scope: str,
    evidence_refs: Iterable[str] = (),
    receipts: Iterable[DestinationReceipt] = (),
    cad_id: str | None = None,
    adr_id: str | None = None,
    bl_id: str | None = None,
    provisional: bool = True,
) -> ChangeEvent:
    if not all(str(value).strip() for value in (action, intent, principal, installation_id, login_surface_id, system_scope)):
        raise ValueError("change event requires action, intent, principal, installation, surface and system scope")
    if not str(agent_id).strip():
        raise ValueError("agent_id is required; use system or explicit agent identity")
    generated = provisional_ids(action=action, intent=intent, principal=principal, installation_id=installation_id)
    ids = (cad_id or generated[0], adr_id or generated[1], bl_id or generated[2])
    receipt_tuple = tuple(receipts)
    status, gap = _status(receipt_tuple)
    return ChangeEvent(
        event_id="EVT-" + _digest(*ids, action, _timestamp()),
        cad_id=ids[0], adr_id=ids[1], bl_id=ids[2], provisional=provisional,
        principal=principal, installation_id=installation_id,
        login_surface_id=login_surface_id, agent_id=agent_id,
        system_scope=system_scope, action=action, intent=intent,
        evidence_refs=tuple(str(ref) for ref in evidence_refs),
        receipts=receipt_tuple, status=status, created_at=_timestamp(), gap=gap,
    )


def update_receipts(event: ChangeEvent, receipts: Iterable[DestinationReceipt]) -> ChangeEvent:
    """Reconcile destination receipts onto the same event identity."""
    receipt_tuple = tuple(receipts)
    status, gap = _status(receipt_tuple)
    return ChangeEvent(
        event_id=event.event_id,
        cad_id=event.cad_id,
        adr_id=event.adr_id,
        bl_id=event.bl_id,
        provisional=event.provisional,
        principal=event.principal,
        installation_id=event.installation_id,
        login_surface_id=event.login_surface_id,
        agent_id=event.agent_id,
        system_scope=event.system_scope,
        action=event.action,
        intent=event.intent,
        evidence_refs=event.evidence_refs,
        receipts=receipt_tuple,
        status=status,
        created_at=event.created_at,
        gap=gap,
    )


def append_event(event: ChangeEvent, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def validate_event_metadata(event: ChangeEvent) -> None:
    """Reject raw payload leakage and false completion claims."""
    data = event.as_dict()
    forbidden = {"raw", "content", "secret", "token", "password", "payload"}
    if forbidden.intersection(data):
        raise ValueError("raw/private change fields are forbidden")
    if event.status is ChangeStatus.COMPLETE and len(event.receipts) < 3:
        raise ValueError("COMPLETE requires git, graph and Obsidian receipts")
