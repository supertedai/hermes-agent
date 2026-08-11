from agent.mwp_autonomy_adapter import (
    mission_from_control_task,
    mission_readback_from_control_task,
)
from agent.mwp_autonomy_envelope import AutonomyLevel
from agent.mwp_control_plane import Axis, ControlTask, TaskState


def task(task_id, *, state=TaskState.READY, dependencies=(), evidence=(), rollback=""):
    return ControlTask(
        mwp_id="MWP-UOSH-001",
        case_id="CASE-AUTONOMY-00",
        task_id=task_id,
        principal_id="morten",
        axis=Axis.SYSTEM,
        state=state,
        dependencies=tuple(dependencies),
        scope="mwp/autonomy",
        evidence_refs=tuple(evidence),
        rollback_ref=rollback,
    )


def test_adapter_projects_existing_task_without_creating_authority():
    current = task("current", evidence=("receipt:test",))
    projected = mission_from_control_task(
        current,
        {current.task_id: current},
        required_evidence_refs=("receipt:test",),
    )
    assert projected.task_id == current.task_id
    assert projected.mission_id == "mission:current"
    assert projected.evidence[0].ref == "receipt:test"
    assert projected.evidence[0].state.value == "REQUIRED"


def test_adapter_requires_explicit_verified_evidence():
    current = task("current")
    result = mission_readback_from_control_task(
        current,
        {current.task_id: current},
        required_evidence_refs=("receipt:test",),
    )
    assert not result.permitted
    assert result.blockers == ("missing evidence: receipt:test",)

    result = mission_readback_from_control_task(
        current,
        {current.task_id: current},
        required_evidence_refs=("receipt:test",),
        verified_evidence_refs=("receipt:test",),
    )
    assert result.permitted


def test_adapter_maps_dependencies_and_closed_state():
    child = task("child", state=TaskState.CLOSED)
    parent = task("parent", dependencies=("child",))
    result = mission_readback_from_control_task(
        parent,
        {child.task_id: child, parent.task_id: parent},
    )
    assert result.permitted
    assert result.missing_dependencies == ()


def test_adapter_preserves_blocked_and_rollback_states():
    blocked = task("blocked", state=TaskState.BLOCKED)
    result = mission_readback_from_control_task(blocked, {blocked.task_id: blocked})
    assert not result.permitted
    assert "mission state blocks execution: BLOCKED" in result.blockers

    rollback = task("rollback", state=TaskState.ROLLBACK_REQUIRED)
    result = mission_readback_from_control_task(rollback, {rollback.task_id: rollback})
    assert not result.permitted
    assert "rollback reference required" in result.blockers


def test_l4_owner_gate_remains_explicit():
    current = task("current")
    result = mission_readback_from_control_task(
        current,
        {current.task_id: current},
        autonomy=AutonomyLevel.L4_OWNER_AUTHORITY,
    )
    assert not result.permitted
    assert result.blockers == ("L4 requires explicit owner gate",)


def test_unknown_task_snapshot_fails_closed():
    current = task("current")
    try:
        mission_from_control_task(current, {})
    except ValueError as exc:
        assert str(exc) == "control task must be present in canonical task snapshot"
    else:
        raise AssertionError("unknown task snapshot must fail closed")
