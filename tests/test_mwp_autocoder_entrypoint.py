from agent.mwp_autocoder_entrypoint import (
    PlanStatus,
    RoleBinding,
    WorkflowRole,
    plan_autocoder_run,
)
from agent.mwp_control_plane import Axis, ControlTask, IdentityMode, TaskState, identity_snapshot


def _task():
    return ControlTask(
        mwp_id="MWP-UOSH-001",
        case_id="CASE-AUTONOMY-00",
        task_id="TASK-WRAPPER-01",
        principal_id="joakim",
        axis=Axis.USER,
        state=TaskState.DISCOVERY,
        scope="mwp/control-plane",
        model_role="sol-design",
    )


def _identity():
    return identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=lambda _sid: "joakim",
        resolve_role=lambda _uid: "user",
        user_exists=lambda _uid: True,
        expected_principal="joakim",
    )


def _roles():
    return (
        RoleBinding(WorkflowRole.DESIGN, "gpt-sol", "openai-api"),
        RoleBinding(WorkflowRole.BUILD, "gpt-luna", "openai-api"),
        RoleBinding(WorkflowRole.REVIEW, "claude-reviewer", "anthropic"),
    )


def test_plan_has_all_thirteen_steps_but_runtime_gate_blocks_execution():
    task = _task()
    plan = plan_autocoder_run(task, {task.task_id: task}, _identity(), _roles())

    assert plan.status is PlanStatus.RUNTIME_UNVERIFIED
    assert plan.complete_sequence
    assert len(plan.steps) == 13
    assert not plan.executor_allowed
    assert plan.side_effects == ()


def test_plan_requires_design_build_and_review_roles():
    task = _task()
    roles = (RoleBinding(WorkflowRole.DESIGN, "gpt-sol", "openai-api"),)
    plan = plan_autocoder_run(task, {task.task_id: task}, _identity(), roles)

    assert plan.status is PlanStatus.BLOCKED
    assert "build" in plan.blocker
    assert not plan.executor_allowed


def test_plan_blocks_identity_before_runtime():
    task = _task()
    blocked = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=lambda _sid: None,
        resolve_role=lambda _uid: "admin",
        user_exists=lambda _uid: True,
    )
    plan = plan_autocoder_run(task, {task.task_id: task}, blocked, _roles())

    assert plan.status is PlanStatus.BLOCKED
    assert plan.principal_id == ""
    assert not plan.executor_allowed


def test_verified_runtime_is_only_a_plan_permission_not_execution():
    task = _task()
    plan = plan_autocoder_run(
        task,
        {task.task_id: task},
        _identity(),
        _roles(),
        runtime_verified=True,
    )

    assert plan.status is PlanStatus.READY
    assert plan.executor_allowed
    assert plan.side_effects == ()
