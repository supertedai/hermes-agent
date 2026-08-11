"""Thin, fail-closed entrypoint contract for the Autocoder 13-step workflow.

This module plans role-separated execution over the existing MWP control-plane
and code-workflow rails. It does not call models, claim tasks, write evidence,
commit, deploy, or activate a scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from agent.mwp_control_plane import (
    AUTOCODER_13_STEPS,
    ControlTask,
    DryRunStatus,
    GateVerdict,
    IdentitySnapshot,
    dependency_status,
    dry_run_13_step,
    gate_for,
)


class WorkflowRole(str, Enum):
    DESIGN = "design"
    BUILD = "build"
    REVIEW = "review"
    SECOND_OPINION = "second_opinion"


class PlanStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    OWNER_GATE = "OWNER_GATE"
    RUNTIME_UNVERIFIED = "RUNTIME_UNVERIFIED"


@dataclass(frozen=True)
class RoleBinding:
    role: WorkflowRole
    model: str
    provider: str

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.provider.strip():
            raise ValueError(f"model and provider are required for {self.role.value}")


@dataclass(frozen=True)
class AutocoderPlan:
    mwp_id: str
    case_id: str
    task_id: str
    principal_id: str
    status: PlanStatus
    blocker: str
    roles: tuple[RoleBinding, ...]
    steps: tuple[str, ...]
    dry_run_statuses: tuple[DryRunStatus, ...]
    executor_allowed: bool
    side_effects: tuple[str, ...] = ()

    @property
    def complete_sequence(self) -> bool:
        return self.steps == AUTOCODER_13_STEPS

    def as_dict(self) -> dict[str, object]:
        return {
            "mwp_id": self.mwp_id,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "principal_id": self.principal_id,
            "status": self.status.value,
            "blocker": self.blocker,
            "roles": [
                {"role": item.role.value, "model": item.model, "provider": item.provider}
                for item in self.roles
            ],
            "steps": list(self.steps),
            "dry_run_statuses": [item.value for item in self.dry_run_statuses],
            "executor_allowed": self.executor_allowed,
            "side_effects": list(self.side_effects),
        }


def plan_autocoder_run(
    task: ControlTask,
    tasks: Mapping[str, ControlTask],
    identity: IdentitySnapshot,
    roles: Sequence[RoleBinding],
    *,
    runtime_verified: bool = False,
) -> AutocoderPlan:
    """Create a metadata-only execution plan without invoking an executor."""
    role_items = tuple(roles)
    role_set = {item.role for item in role_items}
    required_roles = {
        WorkflowRole.DESIGN,
        WorkflowRole.BUILD,
        WorkflowRole.REVIEW,
    }
    if not required_roles.issubset(role_set):
        missing = ", ".join(sorted(role.value for role in required_roles - role_set))
        return _plan(task, identity, PlanStatus.BLOCKED,
                     f"missing required role bindings: {missing}", role_items, tasks)
    if not identity.permitted:
        return _plan(task, identity, PlanStatus.BLOCKED,
                     "; ".join(identity.blockers) or "identity is blocked",
                     role_items, tasks)
    dependency = dependency_status(task, tasks)
    gate = gate_for(task, dependency)
    if gate is not GateVerdict.GO_READ_ONLY:
        return _plan(
            task,
            identity,
            PlanStatus.OWNER_GATE if gate is GateVerdict.OWNER_GATE else PlanStatus.BLOCKED,
            "; ".join(dependency.blockers) or f"task gate is {gate.value}",
            role_items,
            tasks,
        )
    if not runtime_verified:
        return _plan(task, identity, PlanStatus.RUNTIME_UNVERIFIED,
                     "target role/provider runtime is not verified", role_items, tasks)
    return _plan(task, identity, PlanStatus.READY, "", role_items, tasks,
                 executor_allowed=True)


def _plan(
    task: ControlTask,
    identity: IdentitySnapshot,
    status: PlanStatus,
    blocker: str,
    roles: tuple[RoleBinding, ...],
    tasks: Mapping[str, ControlTask],
    *,
    executor_allowed: bool = False,
) -> AutocoderPlan:
    dry_run = dry_run_13_step(task, tasks, identity)
    return AutocoderPlan(
        mwp_id=task.mwp_id,
        case_id=task.case_id,
        task_id=task.task_id,
        principal_id=identity.principal_id,
        status=status,
        blocker=blocker,
        roles=roles,
        steps=AUTOCODER_13_STEPS,
        dry_run_statuses=tuple(step.status for step in dry_run.steps),
        executor_allowed=executor_allowed,
        side_effects=(),
    )
