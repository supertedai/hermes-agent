from agent.dispatcher_adapter import Dispatcher, LeaseState
from agent.mwp_control_plane import Axis, ControlTask, TaskState
from agent.mwp_orchestrator_adapter import OrchestratorAdapter


def task(task_id="lane-1"):
    return ControlTask(
        mwp_id="mwp-1",
        case_id="case-1",
        task_id=task_id,
        principal_id="principal-1",
        axis=Axis.AGENT,
        state=TaskState.READY,
        scope="test",
    )


def test_project_ready_lanes_uses_existing_orchestrator():
    dispatcher = Dispatcher(OrchestratorAdapter([task()]))
    chips = dispatcher.project_ready_lanes()
    assert [chip.task_id for chip in chips] == ["lane-1"]


def test_lease_fails_closed_without_verified_authority():
    dispatcher = Dispatcher(OrchestratorAdapter([task()]), principal_id="principal-1")
    readback = dispatcher.manage_lease()
    assert readback.status == "BLOCKED"
    assert dispatcher.lease_state is LeaseState.FAILED


def test_verified_authority_enables_heartbeat_and_metadata_result():
    dispatcher = Dispatcher(
        OrchestratorAdapter([task()]),
        principal_id="principal-1",
        authority_check=lambda: True,
    )
    assert dispatcher.manage_lease().status == "READY"
    assert dispatcher.heartbeat().status == "HEARTBEAT"
    result = dispatcher.report_result("lane-1", {"status": "verified"})
    assert result.status == "RESULT_RECORDED"
    assert dispatcher.results["lane-1"].result["status"] == "verified"


def test_result_rejects_unknown_task_or_missing_lease():
    dispatcher = Dispatcher(OrchestratorAdapter([task()]))
    assert dispatcher.report_result("lane-1", {}).status == "BLOCKED"
    dispatcher = Dispatcher(
        OrchestratorAdapter([task()]),
        principal_id="principal-1",
        authority_check=lambda: True,
    )
    dispatcher.manage_lease()
    assert dispatcher.report_result("unknown", {}).status == "BLOCKED"
