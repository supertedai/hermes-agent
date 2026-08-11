"""Read-only MWP autonomy control-plane contract.

This module deliberately owns no persistence, scheduler, model calls, or external
writes. It provides a small deterministic contract that can later be adapted to
Kanban, ``agent.code_workflow``, evidence storage, and the Autocoder 13-step
workflow without creating a second task authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class Axis(str, Enum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class TaskState(str, Enum):
    DISCOVERY = "DISCOVERY"
    CLASSIFIED = "CLASSIFIED"
    PLANNED = "PLANNED"
    PREFLIGHT = "PREFLIGHT"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    REVIEW = "REVIEW"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"
    OWNER_GATE = "OWNER_GATE"
    SECURITY_GATE = "SECURITY_GATE"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


class GateVerdict(str, Enum):
    GO_READ_ONLY = "GO_READ_ONLY"
    GO_ISOLATED_WRITE = "GO_ISOLATED_WRITE"
    BLOCK = "BLOCK"
    OWNER_GATE = "OWNER_GATE"


class IdentityMode(str, Enum):
    LEGACY_OWNER = "legacy_owner"
    AUTHENTICATED_MULTIUSER = "authenticated_multiuser"


class IdentityVerdict(str, Enum):
    LEGACY_OWNER = "LEGACY_OWNER"
    AUTHENTICATED = "AUTHENTICATED"
    BLOCK = "BLOCK"


class DryRunStatus(str, Enum):
    PLANNED = "PLANNED"
    NOT_EXECUTED = "NOT_EXECUTED"
    BLOCKED = "BLOCKED"


AUTOCODER_13_STEPS = (
    "directive",
    "job_discovery",
    "ranking_planning_architecture",
    "pre_rails",
    "bl_gate",
    "claim_and_lease",
    "sol_design_review_pass",
    "faber_implementation",
    "governance",
    "canonical_reviewer_gate",
    "landing",
    "runtime_smoke",
    "postcommit_readback",
)

# The top-level sequence remains 13 steps for compatibility. These contracts
# make the bounded-autonomy gates explicit inside the existing steps.
AUTOCODER_13_GATE_CONTRACT = {
    "bl_gate": (
        "MissionEnvelope",
        "CAD/ADR/BL mapping",
        "principal/tenant/scope",
        "dependency graph",
        "rollback reference",
    ),
    "claim_and_lease": (
        "preclaim policy",
        "verified evidence",
        "dependency readiness",
        "canonical claim",
        "lease/heartbeat",
    ),
    "governance": (
        "authority/policy verdict",
        "reviewer or owner gate",
        "no self-approval",
    ),
    "postcommit_readback": (
        "implementation",
        "scoped test",
        "runtime/read-after-write",
        "provenance",
        "outcome",
        "rollback proof",
        "CAD/ADR/BL projection",
    ),
}


_TERMINAL_BLOCKERS = frozenset(
    {
        TaskState.BLOCKED,
        TaskState.OWNER_GATE,
        TaskState.SECURITY_GATE,
        TaskState.ROLLBACK_REQUIRED,
        TaskState.STALE,
        TaskState.CONFLICT,
    }
)


@dataclass(frozen=True)
class ControlTask:
    """Metadata-only task identity and lifecycle input."""

    mwp_id: str
    case_id: str
    task_id: str
    principal_id: str
    axis: Axis
    state: TaskState
    dependencies: tuple[str, ...] = ()
    owner: str = ""
    scope: str = ""
    required_gate: str = ""
    evidence_refs: tuple[str, ...] = ()
    rollback_ref: str = ""
    next_permitted_action: str = ""
    model_role: str = ""

    def __post_init__(self) -> None:
        required = {
            "mwp_id": self.mwp_id,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "principal_id": self.principal_id,
            "scope": self.scope,
        }
        missing = tuple(name for name, value in required.items() if not value.strip())
        if missing:
            raise ValueError("missing control-task fields: " + ", ".join(missing))
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("duplicate task dependencies are not allowed")
        if self.task_id in self.dependencies:
            raise ValueError("a task cannot depend on itself")


@dataclass(frozen=True)
class DependencyResult:
    ready: bool
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlReadback:
    """Metadata-only master readback; no raw memory/code/evidence payloads."""

    mwp_id: str
    case_id: str
    task_id: str
    principal_id: str
    axis: Axis
    state: TaskState
    gate: GateVerdict
    dependency_ready: bool
    blockers: tuple[str, ...]
    evidence_count: int
    has_rollback: bool
    next_permitted_action: str
    model_role: str

    def as_dict(self) -> dict[str, object]:
        return {
            "mwp_id": self.mwp_id,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "principal_id": self.principal_id,
            "axis": self.axis.value,
            "state": self.state.value,
            "gate": self.gate.value,
            "dependency_ready": self.dependency_ready,
            "blockers": list(self.blockers),
            "evidence_count": self.evidence_count,
            "has_rollback": self.has_rollback,
            "next_permitted_action": self.next_permitted_action,
            "model_role": self.model_role,
        }


@dataclass(frozen=True)
class IdentitySnapshot:
    """Read-only principal/session decision with explicit legacy semantics."""

    mode: IdentityMode
    verdict: IdentityVerdict
    principal_id: str
    role: str
    client_session_id: str
    durable_session_id: str
    blockers: tuple[str, ...] = ()

    @property
    def permitted(self) -> bool:
        return self.verdict is not IdentityVerdict.BLOCK


@dataclass(frozen=True)
class DryRunStep:
    number: int
    name: str
    status: DryRunStatus
    gate: GateVerdict
    note: str


@dataclass(frozen=True)
class DryRunResult:
    mwp_id: str
    case_id: str
    task_id: str
    principal_id: str
    identity_verdict: IdentityVerdict
    steps: tuple[DryRunStep, ...]
    side_effects: tuple[str, ...] = ()

    @property
    def complete_sequence(self) -> bool:
        return tuple(step.name for step in self.steps) == AUTOCODER_13_STEPS

    def as_dict(self) -> dict[str, object]:
        return {
            "mwp_id": self.mwp_id,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "principal_id": self.principal_id,
            "identity_verdict": self.identity_verdict.value,
            "steps": [
                {
                    "number": step.number,
                    "name": step.name,
                    "status": step.status.value,
                    "gate": step.gate.value,
                    "note": step.note,
                }
                for step in self.steps
            ],
            "side_effects": list(self.side_effects),
        }



def existing_identity_snapshot(
    *,
    client_session_id: str,
    durable_session_id: str,
    mode: IdentityMode,
    expected_principal: str = "",
) -> IdentitySnapshot:
    """Read the existing Hermes identity/user authorities without writing.

    This is the integration seam for the real stores. It deliberately calls
    only ``get_identity``, ``get_user`` and ``resolve_role``; ``set_identity``
    is not imported or reachable through this function.
    """

    from hermes_cli.dashboard_auth.session_identity import get_identity, resolve_role
    from hermes_cli.dashboard_auth.user_store import get_user

    return identity_snapshot(
        client_session_id=client_session_id,
        durable_session_id=durable_session_id,
        mode=mode,
        read_identity=get_identity,
        resolve_role=resolve_role,
        user_exists=lambda principal: get_user(principal) is not None,
        expected_principal=expected_principal,
    )


def dependency_status(
    task: ControlTask,
    tasks: Mapping[str, ControlTask],
) -> DependencyResult:
    """Return readiness without changing any task or task authority."""

    blockers: list[str] = []
    for dependency_id in task.dependencies:
        dependency = tasks.get(dependency_id)
        if dependency is None:
            blockers.append(f"missing dependency: {dependency_id}")
        elif dependency.state is not TaskState.CLOSED:
            blockers.append(
                f"dependency not closed: {dependency_id} ({dependency.state.value})"
            )
    return DependencyResult(not blockers, tuple(blockers))


def gate_for(
    task: ControlTask,
    dependency: DependencyResult,
) -> GateVerdict:
    """Compute the safe gate for a task from immutable metadata."""

    if task.state in _TERMINAL_BLOCKERS:
        if task.state is TaskState.OWNER_GATE:
            return GateVerdict.OWNER_GATE
        return GateVerdict.BLOCK
    if not dependency.ready:
        return GateVerdict.BLOCK
    if task.required_gate:
        return GateVerdict.OWNER_GATE
    return GateVerdict.GO_READ_ONLY


def readback(
    task: ControlTask,
    tasks: Mapping[str, ControlTask],
) -> ControlReadback:
    """Build the metadata-only readback used by the MWP master index."""

    dependency = dependency_status(task, tasks)
    gate = gate_for(task, dependency)
    blockers = list(dependency.blockers)
    if task.state in _TERMINAL_BLOCKERS and task.state is not TaskState.OWNER_GATE:
        blockers.append(f"task state blocks execution: {task.state.value}")
    if task.state is TaskState.OWNER_GATE or task.required_gate:
        blockers.append(task.required_gate or "owner gate required")
    next_action = task.next_permitted_action
    if not next_action:
        next_action = (
            "continue read-only discovery"
            if gate is GateVerdict.GO_READ_ONLY
            else "resolve blockers before proceeding"
        )
    return ControlReadback(
        mwp_id=task.mwp_id,
        case_id=task.case_id,
        task_id=task.task_id,
        principal_id=task.principal_id,
        axis=task.axis,
        state=task.state,
        gate=gate,
        dependency_ready=dependency.ready,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_count=len(task.evidence_refs),
        has_rollback=bool(task.rollback_ref),
        next_permitted_action=next_action,
        model_role=task.model_role,
    )


def readbacks(
    tasks: Sequence[ControlTask],
) -> tuple[ControlReadback, ...]:
    """Build deterministic readbacks for a task snapshot."""

    by_id = {task.task_id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("duplicate task_id in control-plane snapshot")
    return tuple(readback(task, by_id) for task in tasks)


_KANBAN_STATE_MAP = {
    "triage": TaskState.DISCOVERY,
    "todo": TaskState.PLANNED,
    "scheduled": TaskState.READY,
    "ready": TaskState.READY,
    "running": TaskState.RUNNING,
    "blocked": TaskState.BLOCKED,
    "review": TaskState.REVIEW,
    "done": TaskState.CLOSED,
    "archived": TaskState.STALE,
}


def control_task_from_kanban(
    kanban_task: object,
    *,
    mwp_id: str,
    case_id: str,
    principal_id: str,
    axis: Axis,
    scope: str,
    dependencies: Sequence[str] = (),
    required_gate: str = "",
    evidence_refs: Sequence[str] = (),
    rollback_ref: str = "",
    model_role: str = "",
) -> ControlTask:
    """Project an existing Kanban task without creating a second task record.

    Principal, axis, scope, dependencies and evidence are explicit inputs on
    purpose. Kanban's ``assignee``/``created_by`` fields are not authoritative
    enough to infer the MWP principal or ASI axis.
    """

    task_id = str(getattr(kanban_task, "id", "") or "")
    status = str(getattr(kanban_task, "status", "") or "").strip().lower()
    if not task_id:
        raise ValueError("Kanban task has no stable id")
    try:
        state = _KANBAN_STATE_MAP[status]
    except KeyError as exc:
        raise ValueError(f"unsupported Kanban status: {status or '<empty>'}") from exc
    return ControlTask(
        mwp_id=mwp_id,
        case_id=case_id,
        task_id=task_id,
        principal_id=principal_id,
        axis=axis,
        state=state,
        dependencies=tuple(dependencies),
        owner=str(getattr(kanban_task, "assignee", "") or ""),
        scope=scope,
        required_gate=required_gate,
        evidence_refs=tuple(evidence_refs),
        rollback_ref=rollback_ref,
        next_permitted_action="",
        model_role=model_role,
    )


def identity_snapshot(
    *,
    client_session_id: str,
    durable_session_id: str,
    mode: IdentityMode,
    read_identity,
    resolve_role,
    user_exists,
    expected_principal: str = "",
) -> IdentitySnapshot:
    """Resolve principal scope without implicit owner fallback.

    ``read_identity`` and the other callbacks are injected so this contract can
    be tested without writing the real identity store. In production they map
    to the existing ``session_identity`` and ``user_store`` readers.
    """

    client_sid = client_session_id.strip()
    durable_sid = durable_session_id.strip()
    if not client_sid or not durable_sid:
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            ("client and durable session IDs are both required",),
        )
    try:
        client_principal = (read_identity(client_sid) or "").strip().lower()
        durable_principal = (read_identity(durable_sid) or "").strip().lower()
    except Exception as exc:
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            (f"identity read failed: {type(exc).__name__}",),
        )

    if mode is IdentityMode.LEGACY_OWNER:
        if client_principal or durable_principal:
            return IdentitySnapshot(
                mode,
                IdentityVerdict.BLOCK,
                "",
                "user",
                client_sid,
                durable_sid,
                ("legacy owner mode cannot carry an authenticated principal",),
            )
        return IdentitySnapshot(
            mode,
            IdentityVerdict.LEGACY_OWNER,
            "morten",
            "admin",
            client_sid,
            durable_sid,
        )

    if not client_principal or not durable_principal:
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            ("authenticated multiuser session identity is missing",),
        )
    if client_principal != durable_principal:
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            ("client and durable session principals differ",),
        )
    if expected_principal and client_principal != expected_principal.strip().lower():
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            ("resolved principal differs from expected principal",),
        )
    try:
        exists = bool(user_exists(client_principal))
        role = str(resolve_role(client_principal) or "user")
    except Exception as exc:
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            (f"user authority read failed: {type(exc).__name__}",),
        )
    if not exists:
        return IdentitySnapshot(
            mode,
            IdentityVerdict.BLOCK,
            "",
            "user",
            client_sid,
            durable_sid,
            ("resolved principal is not present in canonical user store",),
        )
    return IdentitySnapshot(
        mode,
        IdentityVerdict.AUTHENTICATED,
        client_principal,
        role,
        client_sid,
        durable_sid,
    )


def dry_run_13_step(
    task: ControlTask,
    tasks: Mapping[str, ControlTask],
    identity: IdentitySnapshot,
) -> DryRunResult:
    """Plan all 13 Autocoder stages without executing side effects."""

    dependency = dependency_status(task, tasks)
    task_gate = gate_for(task, dependency)
    permitted = identity.permitted and task_gate is GateVerdict.GO_READ_ONLY
    planned_names = {
        "directive",
        "job_discovery",
        "ranking_planning_architecture",
        "pre_rails",
        "bl_gate",
        "sol_design_review_pass",
        "governance",
        "canonical_reviewer_gate",
    }
    notes = {
        "claim_and_lease": "dry-run: claim/lease not executed",
        "faber_implementation": "dry-run: build not executed",
        "landing": "dry-run: landing not executed",
        "runtime_smoke": "dry-run: runtime smoke not executed",
        "postcommit_readback": "dry-run: postcommit not executed",
    }
    steps: list[DryRunStep] = []
    for number, name in enumerate(AUTOCODER_13_STEPS, start=1):
        if not permitted:
            status = DryRunStatus.BLOCKED if number == 1 else DryRunStatus.NOT_EXECUTED
            note = "identity or task gate blocks dry-run" if number == 1 else "not reached"
            gate = GateVerdict.BLOCK
        elif name in planned_names:
            status = DryRunStatus.PLANNED
            note = "stage contract and gate planned; no executor invoked"
            gate = GateVerdict.GO_READ_ONLY
        else:
            status = DryRunStatus.NOT_EXECUTED
            note = notes.get(name, "dry-run: stage not executed")
            gate = GateVerdict.GO_READ_ONLY
        steps.append(DryRunStep(number, name, status, gate, note))
    return DryRunResult(
        mwp_id=task.mwp_id,
        case_id=task.case_id,
        task_id=task.task_id,
        principal_id=identity.principal_id,
        identity_verdict=identity.verdict,
        steps=tuple(steps),
        side_effects=(),
    )


def verification_evidence_ref(
    evidence: object,
    *,
    task_id: str,
) -> str:
    """Create a stable metadata reference to an existing evidence record.

    The evidence ledger remains the source of truth. This function does not
    persist, copy output, or infer a task from a command. Callers must provide
    the MWP task ID explicitly and the source record must provide its session,
    kind, scope and canonical command.
    """

    if not task_id.strip():
        raise ValueError("task_id is required for evidence mapping")
    required = {
        "session_id": getattr(evidence, "session_id", ""),
        "kind": getattr(evidence, "kind", ""),
        "scope": getattr(evidence, "scope", ""),
        "canonical_command": getattr(evidence, "canonical_command", ""),
    }
    missing = tuple(name for name, value in required.items() if not str(value).strip())
    if missing:
        raise ValueError("evidence is missing mapping fields: " + ", ".join(missing))
    return "evidence:{task}:{session}:{kind}:{scope}:{command}".format(
        task=task_id.strip(),
        session=str(required["session_id"]).strip(),
        kind=str(required["kind"]).strip(),
        scope=str(required["scope"]).strip(),
        command=str(required["canonical_command"]).strip(),
    )
