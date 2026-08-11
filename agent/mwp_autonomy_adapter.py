"""Adapter from the existing MWP ControlTask to MissionEnvelope.

The existing ControlTask/Kanban projection remains authoritative. This module
only creates a deterministic metadata projection and never persists, leases,
executes, schedules, or writes to an external system.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from agent.mwp_autonomy_envelope import (
    AutonomyLevel,
    EvidenceRef,
    EvidenceState,
    MissionEnvelope,
    MissionReadback,
    MissionState,
    RecoveryMode,
    evaluate_mission,
)
from agent.mwp_control_plane import ControlTask, TaskState


_STATE_MAP = {
    TaskState.DISCOVERY: MissionState.PLANNED,
    TaskState.CLASSIFIED: MissionState.PLANNED,
    TaskState.PLANNED: MissionState.PLANNED,
    TaskState.PREFLIGHT: MissionState.READY,
    TaskState.READY: MissionState.READY,
    TaskState.CLAIMED: MissionState.RUNNING,
    TaskState.RUNNING: MissionState.RUNNING,
    TaskState.VERIFYING: MissionState.VERIFYING,
    TaskState.REVIEW: MissionState.VERIFYING,
    TaskState.CLOSED: MissionState.COMPLETE,
    TaskState.BLOCKED: MissionState.BLOCKED,
    TaskState.OWNER_GATE: MissionState.BLOCKED,
    TaskState.SECURITY_GATE: MissionState.BLOCKED,
    TaskState.ROLLBACK_REQUIRED: MissionState.RECOVERY,
    TaskState.STALE: MissionState.BLOCKED,
    TaskState.CONFLICT: MissionState.BLOCKED,
}


def mission_from_control_task(
    task: ControlTask,
    tasks: Mapping[str, ControlTask],
    *,
    autonomy: AutonomyLevel = AutonomyLevel.L1_PLAN,
    verified_evidence_refs: Iterable[str] = (),
    required_evidence_refs: Iterable[str] = (),
    checkpoint_ref: str = "",
    owner_gate: str = "",
) -> MissionEnvelope:
    """Project an existing ControlTask without creating a second task record."""
    if task.task_id not in tasks:
        raise ValueError("control task must be present in canonical task snapshot")
    verified = set(verified_evidence_refs)
    required = tuple(dict.fromkeys(str(ref) for ref in required_evidence_refs))
    evidence = tuple(
        EvidenceRef(ref, EvidenceState.VERIFIED if ref in verified else EvidenceState.REQUIRED)
        for ref in required
    )
    closed_dependencies = tuple(
        dependency_id
        for dependency_id in task.dependencies
        if dependency_id in tasks and tasks[dependency_id].state is TaskState.CLOSED
    )
    recovery = (
        RecoveryMode.ROLLBACK_REQUIRED
        if task.state is TaskState.ROLLBACK_REQUIRED
        else RecoveryMode.NONE
    )
    return MissionEnvelope(
        mission_id=f"mission:{task.task_id}",
        mwp_id=task.mwp_id,
        case_id=task.case_id,
        task_id=task.task_id,
        principal_id=task.principal_id,
        scope=task.scope,
        autonomy=autonomy,
        state=_STATE_MAP[task.state],
        dependencies=tuple(task.dependencies),
        completed_dependencies=closed_dependencies,
        evidence=evidence,
        checkpoint_ref=checkpoint_ref,
        rollback_ref=task.rollback_ref,
        recovery=recovery,
        owner_gate=owner_gate or (task.required_gate if task.state is TaskState.OWNER_GATE else ""),
    )


def mission_readback_from_control_task(
    task: ControlTask,
    tasks: Mapping[str, ControlTask],
    *,
    autonomy: AutonomyLevel = AutonomyLevel.L1_PLAN,
    verified_evidence_refs: Sequence[str] = (),
    required_evidence_refs: Sequence[str] = (),
    checkpoint_ref: str = "",
    owner_gate: str = "",
) -> MissionReadback:
    """Return the bounded-autonomy readback for an existing control task."""
    mission = mission_from_control_task(
        task,
        tasks,
        autonomy=autonomy,
        verified_evidence_refs=verified_evidence_refs,
        required_evidence_refs=required_evidence_refs,
        checkpoint_ref=checkpoint_ref,
        owner_gate=owner_gate,
    )
    return evaluate_mission(mission, required_evidence=required_evidence_refs)
