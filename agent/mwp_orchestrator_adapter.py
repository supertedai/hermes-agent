"""Metadata-only mission orchestration over the canonical MWP task snapshot.

This adapter does not create a second task authority. It projects an existing
ControlTask mapping into independent lanes, calculates which lanes are ready,
and emits bounded chip-like events for a UI or supervisor. Live claims,
workers, graph/Obsidian writes, and deployment remain outside this boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent.mwp_control_plane import ControlTask, TaskState, dependency_status
from agent.mwp_loop_starter import LoopReadback, LoopStatus


@dataclass(frozen=True)
class MissionChip:
    task_id: str
    parent_task_id: str | None
    lane: str
    status: LoopStatus
    blocker: str = ""
    next_action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "lane": self.lane,
            "status": self.status.value,
            "blocker": self.blocker,
            "next_action": self.next_action,
        }


class OrchestratorAdapter:
    """Project an existing task graph into independent executable lanes."""

    def __init__(self, tasks: Mapping[str, ControlTask] | Sequence[ControlTask], *, parent_task_id: str | None = None) -> None:
        values = tasks.values() if isinstance(tasks, Mapping) else tasks
        self.tasks: dict[str, ControlTask] = {task.task_id: task for task in values}
        self.parent_task_id = parent_task_id
        self.readbacks: dict[str, LoopReadback] = {}
        self.chips: tuple[MissionChip, ...] = ()

    def calculate_states(self) -> Mapping[str, LoopReadback]:
        readbacks: dict[str, LoopReadback] = {}
        chips: list[MissionChip] = []
        blocked_states = {
            TaskState.BLOCKED,
            TaskState.OWNER_GATE,
            TaskState.SECURITY_GATE,
            TaskState.ROLLBACK_REQUIRED,
            TaskState.STALE,
            TaskState.CONFLICT,
        }
        for task_id, task in self.tasks.items():
            if task.state is TaskState.CLOSED:
                status, blocker, next_action = LoopStatus.COMPLETE, "", "parent may join this lane"
            elif task.state in blocked_states:
                status = LoopStatus.BLOCKED
                blocker = task.required_gate or task.next_permitted_action or task.state.value
                next_action = task.next_permitted_action or "resolve this lane blocker"
            else:
                dependency = dependency_status(task, self.tasks)
                if dependency.ready:
                    status, blocker, next_action = LoopStatus.RUNNING, "", "dispatch or continue this independent lane"
                else:
                    status = LoopStatus.BLOCKED
                    blocker = "; ".join(dependency.blockers)
                    next_action = "wait for dependencies; continue unrelated ready lanes"
            readback = LoopReadback(
                loop_id=task_id,
                status=status,
                ticks=0,
                blocker=blocker,
                next_action=next_action,
                last_readback={
                    "task_id": task_id,
                    "parent_task_id": self.parent_task_id,
                    "lane": task.axis.value,
                    "task_state": task.state.value,
                    "dependencies": list(task.dependencies),
                },
            )
            readbacks[task_id] = readback
            chips.append(MissionChip(task_id, self.parent_task_id, task.axis.value, status, blocker, next_action))
        self.readbacks = readbacks
        self.chips = tuple(chips)
        return dict(readbacks)

    def ready_lane_ids(self) -> tuple[str, ...]:
        if not self.readbacks:
            self.calculate_states()
        return tuple(task_id for task_id, readback in self.readbacks.items() if readback.status is LoopStatus.RUNNING)

    def emit_events(self) -> tuple[dict[str, Any], ...]:
        if not self.chips:
            self.calculate_states()
        return tuple({"type": "mission.chip", "payload": chip.as_dict()} for chip in self.chips)

    def parent_status(self) -> LoopStatus:
        if not self.readbacks:
            self.calculate_states()
        statuses = tuple(item.status for item in self.readbacks.values())
        if statuses and all(status is LoopStatus.COMPLETE for status in statuses):
            return LoopStatus.COMPLETE
        if any(status is LoopStatus.RUNNING for status in statuses):
            return LoopStatus.RUNNING
        if any(status is LoopStatus.BLOCKED for status in statuses):
            return LoopStatus.BLOCKED
        return LoopStatus.RUNNING
