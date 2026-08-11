"""Fail-closed metadata dispatcher over the existing mission lanes.

This module does not create Kanban tasks or perform worker claims. It provides
the seam where a verified canonical authority can later be attached, while
making lease/heartbeat/result state explicit and testable now.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from agent.mwp_orchestrator_adapter import MissionChip, OrchestratorAdapter
from agent.mwp_loop_starter import LoopStatus


class LeaseState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DispatchReadback:
    status: str
    lease: LeaseState
    task_id: str = ""
    blocker: str = ""
    result: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "lease": self.lease.value,
            "task_id": self.task_id,
            "blocker": self.blocker,
            "result": dict(self.result),
        }


@dataclass
class Dispatcher:
    orchestrator: OrchestratorAdapter
    principal_id: str = ""
    authority_check: Callable[[], bool] | None = None
    lease_state: LeaseState = LeaseState.UNVERIFIED
    heartbeat_count: int = 0
    results: dict[str, DispatchReadback] = field(default_factory=dict)

    def project_ready_lanes(self) -> tuple[MissionChip, ...]:
        """Project all ready lanes; blocked siblings remain visible, not fatal."""
        self.orchestrator.calculate_states()
        ready = set(self.orchestrator.ready_lane_ids())
        return tuple(chip for chip in self.orchestrator.chips if chip.task_id in ready)

    def is_authoritative(self) -> bool:
        return bool(self.principal_id.strip()) and bool(
            self.authority_check() if self.authority_check is not None else False
        )

    def manage_lease(self) -> DispatchReadback:
        """Acquire/retain only a verified lease; never infer authority."""
        if not self.is_authoritative():
            self.lease_state = LeaseState.FAILED
            return DispatchReadback(
                status="BLOCKED",
                lease=self.lease_state,
                blocker="canonical authority or principal is not verified",
            )
        self.lease_state = LeaseState.ACTIVE
        return DispatchReadback(status="READY", lease=self.lease_state)

    def heartbeat(self) -> DispatchReadback:
        if self.lease_state is not LeaseState.ACTIVE:
            return DispatchReadback(
                status="BLOCKED",
                lease=self.lease_state,
                blocker="no active verified lease",
            )
        self.heartbeat_count += 1
        return DispatchReadback(
            status="HEARTBEAT",
            lease=self.lease_state,
            result={"heartbeat_count": self.heartbeat_count},
        )

    def report_result(self, task_id: str, result: Mapping[str, Any]) -> DispatchReadback:
        """Record bounded metadata only; reject results without an active lease."""
        if self.lease_state is not LeaseState.ACTIVE:
            return DispatchReadback(
                status="BLOCKED",
                lease=self.lease_state,
                task_id=task_id,
                blocker="cannot report result without active verified lease",
            )
        if task_id not in self.orchestrator.tasks:
            return DispatchReadback(
                status="BLOCKED",
                lease=self.lease_state,
                task_id=task_id,
                blocker="task is not present in canonical orchestrator snapshot",
            )
        readback = DispatchReadback(
            status="RESULT_RECORDED",
            lease=self.lease_state,
            task_id=task_id,
            result=dict(result),
        )
        self.results[task_id] = readback
        return readback
