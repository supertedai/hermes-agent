from agent.mwp_autonomy_envelope import (
    AutonomyLevel,
    EvidenceRef,
    EvidenceState,
    MissionEnvelope,
    MissionState,
    RecoveryMode,
    evaluate_mission,
    validate_dependency_graph,
)


def mission(**overrides):
    values = {
        "mission_id": "mission-1",
        "mwp_id": "MWP-UOSH-001",
        "case_id": "CASE-AUTONOMY-00",
        "task_id": "task-1",
        "principal_id": "morten",
        "scope": "mwp/autonomy",
        "autonomy": AutonomyLevel.L2_ISOLATED_EXECUTE,
        "state": MissionState.READY,
    }
    values.update(overrides)
    return MissionEnvelope(**values)


def test_ready_mission_requires_no_side_effect_and_is_permitted():
    result = evaluate_mission(mission())
    assert result.permitted
    assert result.blockers == ()
    assert result.next_action == "continue within existing MWP task authority"


def test_dependency_and_evidence_gates_fail_closed():
    result = evaluate_mission(
        mission(dependencies=("task-0",)),
        required_evidence=("receipt:test",),
    )
    assert not result.permitted
    assert result.missing_dependencies == ("task-0",)
    assert "dependencies not closed: task-0" in result.blockers
    assert "missing evidence: receipt:test" in result.blockers


def test_verified_evidence_and_closed_dependency_open_execution():
    result = evaluate_mission(
        mission(
            dependencies=("task-0",),
            evidence=(EvidenceRef("receipt:test", EvidenceState.VERIFIED),),
        ),
        closed_tasks=("task-0",),
        required_evidence=("receipt:test",),
    )
    assert result.permitted
    assert result.verified_evidence == 1
    assert result.required_evidence == 1


def test_l4_requires_owner_gate():
    result = evaluate_mission(mission(autonomy=AutonomyLevel.L4_OWNER_AUTHORITY))
    assert not result.permitted
    assert result.blockers == ("L4 requires explicit owner gate",)


def test_failed_evidence_blocks_without_claiming_completion():
    result = evaluate_mission(
        mission(evidence=(EvidenceRef("receipt:test", EvidenceState.FAILED),)),
        required_evidence=("receipt:test",),
    )
    assert not result.permitted
    assert result.blockers == ("failed evidence: receipt:test",)
    assert result.next_action == "resolve blockers; do not claim completion"


def test_rollback_required_needs_reference():
    result = evaluate_mission(
        mission(recovery=RecoveryMode.ROLLBACK_REQUIRED),
    )
    assert not result.permitted
    assert "rollback reference required" in result.blockers


def test_recovery_mode_blocks_resume_until_explicitly_reconciled():
    result = evaluate_mission(
        mission(state=MissionState.RECOVERY, checkpoint_ref="checkpoint:1", rollback_ref="rollback:1")
    )
    assert not result.permitted
    assert "mission state blocks execution: RECOVERY" in result.blockers


def test_dependency_graph_rejects_unknown_dependency_and_cycles():
    try:
        validate_dependency_graph({"a": mission(mission_id="a", dependencies=("missing",))})
    except ValueError as exc:
        assert str(exc) == "unknown mission dependencies: missing"
    else:
        raise AssertionError("unknown dependency must fail closed")

    a = mission(mission_id="a", dependencies=("b",))
    b = mission(mission_id="b", dependencies=("a",))
    try:
        validate_dependency_graph({"a": a, "b": b})
    except ValueError as exc:
        assert str(exc) == "mission dependency cycle detected"
    else:
        raise AssertionError("cycle must fail closed")


def test_readback_is_metadata_only():
    payload = evaluate_mission(mission()).as_dict()
    assert "raw" not in payload
    assert "content" not in payload
    assert "secret" not in payload
