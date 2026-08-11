"""Metadata-only bounded-autonomy mission envelope for MWP-UOSH.

This adapts the useful parts of restart-safe mission runners (explicit mission
contract, autonomy levels, dependency readiness, evidence gating and recovery)
without creating a second task authority, scheduler, writer or executor.
Existing Kanban/MWP task state remains authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class AutonomyLevel(str, Enum):
    L0_OBSERVE = "L0"
    L1_PLAN = "L1"
    L2_ISOLATED_EXECUTE = "L2"
    L3_REVERSIBLE_PROJECT = "L3"
    L4_OWNER_AUTHORITY = "L4"


class MissionState(str, Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    RECOVERY = "RECOVERY"
    COMPLETE = "COMPLETE"


class EvidenceState(str, Enum):
    REQUIRED = "REQUIRED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class RecoveryMode(str, Enum):
    NONE = "NONE"
    RESUME_FROM_CHECKPOINT = "RESUME_FROM_CHECKPOINT"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    OWNER_REVIEW = "OWNER_REVIEW"


@dataclass(frozen=True)
class EvidenceRef:
    ref: str
    state: EvidenceState

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise ValueError("evidence ref is required")


@dataclass(frozen=True)
class MissionEnvelope:
    """A deterministic, metadata-only mission contract.

    ``task_id`` points to the existing canonical task/case authority. This
    object never claims that a task was created, leased, executed or committed.
    """

    mission_id: str
    mwp_id: str
    case_id: str
    task_id: str
    principal_id: str
    scope: str
    autonomy: AutonomyLevel
    state: MissionState
    dependencies: tuple[str, ...] = ()
    completed_dependencies: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    checkpoint_ref: str = ""
    rollback_ref: str = ""
    recovery: RecoveryMode = RecoveryMode.NONE
    owner_gate: str = ""

    def __post_init__(self) -> None:
        required = {
            "mission_id": self.mission_id,
            "mwp_id": self.mwp_id,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "principal_id": self.principal_id,
            "scope": self.scope,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise ValueError("missing mission fields: " + ", ".join(missing))
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("duplicate mission dependencies are not allowed")
        if self.mission_id in self.dependencies:
            raise ValueError("mission cannot depend on itself")
        if len({item.ref for item in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence refs are not allowed")


@dataclass(frozen=True)
class MissionReadback:
    mission_id: str
    state: MissionState
    permitted: bool
    blockers: tuple[str, ...]
    missing_dependencies: tuple[str, ...]
    verified_evidence: int
    required_evidence: int
    recovery: RecoveryMode
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "mission_id": self.mission_id,
            "state": self.state.value,
            "permitted": self.permitted,
            "blockers": list(self.blockers),
            "missing_dependencies": list(self.missing_dependencies),
            "verified_evidence": self.verified_evidence,
            "required_evidence": self.required_evidence,
            "recovery": self.recovery.value,
            "next_action": self.next_action,
        }


def evaluate_mission(
    mission: MissionEnvelope,
    *,
    closed_tasks: Iterable[str] = (),
    required_evidence: Iterable[str] = (),
) -> MissionReadback:
    """Evaluate readiness; never mutates task authority or performs actions."""
    closed = set(closed_tasks) | set(mission.completed_dependencies)
    missing = tuple(dep for dep in mission.dependencies if dep not in closed)
    evidence_by_ref = {item.ref: item for item in mission.evidence}
    required = tuple(dict.fromkeys(str(ref) for ref in required_evidence))
    blockers: list[str] = []

    if missing:
        blockers.append("dependencies not closed: " + ", ".join(missing))
    missing_evidence = tuple(
        ref for ref in required
        if evidence_by_ref.get(ref) is None
        or evidence_by_ref[ref].state is EvidenceState.REQUIRED
    )
    failed_evidence = tuple(
        ref for ref in required if evidence_by_ref.get(ref) is not None
        and evidence_by_ref[ref].state is EvidenceState.FAILED
    )
    if missing_evidence:
        blockers.append("missing evidence: " + ", ".join(missing_evidence))
    if failed_evidence:
        blockers.append("failed evidence: " + ", ".join(failed_evidence))
    if mission.autonomy is AutonomyLevel.L4_OWNER_AUTHORITY and not mission.owner_gate:
        blockers.append("L4 requires explicit owner gate")
    if mission.state in {MissionState.BLOCKED, MissionState.RECOVERY}:
        blockers.append("mission state blocks execution: " + mission.state.value)
    if mission.recovery is RecoveryMode.ROLLBACK_REQUIRED and not mission.rollback_ref:
        blockers.append("rollback reference required")

    permitted = not blockers and mission.state not in {MissionState.COMPLETE, MissionState.VERIFYING}
    if mission.state is MissionState.COMPLETE:
        next_action = "none; preserve canonical task state"
    elif blockers:
        next_action = "resolve blockers; do not claim completion"
    elif mission.autonomy is AutonomyLevel.L0_OBSERVE:
        next_action = "continue metadata-only observation"
    else:
        next_action = "continue within existing MWP task authority"
    return MissionReadback(
        mission_id=mission.mission_id,
        state=mission.state,
        permitted=permitted,
        blockers=tuple(blockers),
        missing_dependencies=missing,
        verified_evidence=sum(item.state is EvidenceState.VERIFIED for item in mission.evidence),
        required_evidence=len(required),
        recovery=mission.recovery,
        next_action=next_action,
    )


def validate_dependency_graph(missions: Mapping[str, MissionEnvelope]) -> None:
    """Reject duplicate IDs, unknown references and dependency cycles."""
    if len(missions) != len(set(missions)):
        raise ValueError("duplicate mission IDs are not allowed")
    for mission in missions.values():
        unknown = sorted(set(mission.dependencies) - set(missions))
        if unknown:
            raise ValueError("unknown mission dependencies: " + ", ".join(unknown))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(mission_id: str) -> None:
        if mission_id in visiting:
            raise ValueError("mission dependency cycle detected")
        if mission_id in visited:
            return
        visiting.add(mission_id)
        for dependency in missions[mission_id].dependencies:
            visit(dependency)
        visiting.remove(mission_id)
        visited.add(mission_id)

    for mission_id in missions:
        visit(mission_id)
