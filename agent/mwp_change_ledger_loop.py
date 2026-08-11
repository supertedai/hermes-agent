"""Bridge change-ledger states into the MWP continuation loop."""
from __future__ import annotations

from typing import Any, Mapping

from agent.mwp_change_ledger import ChangeEvent, ChangeStatus
from agent.mwp_loop_starter import LoopTick


def tick_for_change_event(
    event: ChangeEvent,
    *,
    readback: Mapping[str, Any] | None = None,
    next_action: str = "",
) -> LoopTick:
    """Convert a ledger event into a non-stopping or stopping loop tick.

    OPEN means receipts or independent lanes remain outstanding and therefore
    must continue. BLOCKED is a hard gate for this lane, but the parent
    orchestrator can continue other lanes. COMPLETE only means this event has
    all required destination receipts; it never closes the parent goal alone.
    """
    metadata = dict(readback or {})
    metadata.update({
        "event_id": event.event_id,
        "cad_id": event.cad_id,
        "adr_id": event.adr_id,
        "bl_id": event.bl_id,
        "ledger_status": event.status.value,
        "gap": event.gap,
    })
    if event.status is ChangeStatus.OPEN:
        return LoopTick(
            readback=metadata,
            blocker=event.gap,
            next_action=next_action or "continue independent lanes and retry missing receipts",
            continue_loop=True,
        )
    if event.status is ChangeStatus.BLOCKED:
        return LoopTick(
            readback=metadata,
            blocker=event.gap,
            next_action=next_action or "resolve the lane blocker, keep unrelated lanes running",
            continue_loop=False,
        )
    return LoopTick(readback=metadata, next_action=next_action or "continue parent coverage")
