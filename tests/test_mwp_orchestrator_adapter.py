from dataclasses import replace

from agent.mwp_control_plane import Axis, ControlTask, TaskState
from agent.mwp_loop_starter import LoopStatus
from agent.mwp_orchestrator_adapter import OrchestratorAdapter


def make_task(task_id: str, *, state: TaskState = TaskState.READY, dependencies=()):
    return ControlTask(
        mwp_id="mwp-1",
        case_id="case-1",
        task_id=task_id,
        principal_id="agent-1",
        axis=Axis.AGENT,
        state=state,
        scope="test",
        dependencies=tuple(dependencies),
    )


def test_independent_ready_lanes_are_returned_together():
    adapter = OrchestratorAdapter(
        [
            make_task("task-1"),
            make_task("task-2"),
            make_task("task-3", dependencies=("task-1",)),
        ],
        parent_task_id="parent-1",
    )
    adapter.calculate_states()
    assert adapter.ready_lane_ids() == ("task-1", "task-2")
    assert adapter.parent_status() is LoopStatus.RUNNING
    events = adapter.emit_events()
    assert len(events) == 3
    assert all(event["type"] == "mission.chip" for event in events)


def test_blocked_lane_does_not_stop_unrelated_lane():
    adapter = OrchestratorAdapter(
        [
            make_task("blocked", state=TaskState.BLOCKED),
            make_task("ready"),
        ]
    )
    adapter.calculate_states()
    assert adapter.ready_lane_ids() == ("ready",)
    assert adapter.readbacks["blocked"].status is LoopStatus.BLOCKED
    assert adapter.parent_status() is LoopStatus.RUNNING


def test_dependency_lane_becomes_ready_when_dependency_is_closed():
    adapter = OrchestratorAdapter(
        [make_task("done", state=TaskState.CLOSED), make_task("child", dependencies=("done",))]
    )
    adapter.calculate_states()
    assert adapter.readbacks["done"].status is LoopStatus.COMPLETE
    assert adapter.readbacks["child"].status is LoopStatus.RUNNING


def test_parent_completes_only_when_all_lanes_are_closed():
    adapter = OrchestratorAdapter([make_task("a", state=TaskState.CLOSED), make_task("b")])
    adapter.calculate_states()
    assert adapter.parent_status() is LoopStatus.RUNNING
    adapter.tasks["b"] = replace(adapter.tasks["b"], state=TaskState.CLOSED)
    adapter.calculate_states()
    assert adapter.parent_status() is LoopStatus.COMPLETE
