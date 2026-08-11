"""Fail-closed ASI closeout evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agent.mwp_asi_alignment_registry import ASIAlignmentReadback, ASIStatus


@dataclass(frozen=True)
class CloseoutReadback:
    status: str
    blockers: tuple[str, ...]
    continue_loop: bool
    registry_status: str
    receipt_statuses: tuple[str, ...]


def evaluate_closeout(registry: ASIAlignmentReadback, receipt_statuses: Iterable[str]) -> CloseoutReadback:
    statuses = tuple(receipt_statuses)
    blockers = [f"registry:{row.key}:{row.status.value}" for row in registry.rows if row.status not in {ASIStatus.LIVE_VERIFIED, ASIStatus.CONNECTED_READ_ONLY}]
    blockers.extend(f"receipt:{status}" for status in statuses if status != "VERIFIED")
    if not statuses:
        blockers.append("receipts:missing")
    return CloseoutReadback(
        status="COMPLETE" if not blockers else "OPEN",
        blockers=tuple(blockers),
        continue_loop=bool(blockers),
        registry_status=registry.status,
        receipt_statuses=statuses,
    )
