import pytest

from agent.code_workflow import (
    DefinitionOfDone,
    FaberGoal,
    FaberGoalRegistry,
    GovernedCodeRunner,
    GoalLedger,
    GoalState,
    HandoffStore,
    LandingEvidence,
    PreflightGate,
    PreflightInput,
    PreflightStatus,
    ReviewVerdict,
    ReviewEvidence,
)


def passing_preflight():
    return PreflightGate().evaluate(
        PreflightInput(
            git_clean=True,
            lease_clear=True,
            cad_status="verified",
            adr_status="accepted",
            bl_status="open",
            obsidian_status="fresh",
            source_refs={
                "git": "HEAD:target",
                "lease": "lease:faber",
                "cad": "CAD-M",
                "adr": "ADR-038",
                "bl": "BL-3254",
                "obsidian": "Brain/Change Log.md",
            },
        )
    )


def test_preflight_blocks_reconstructed_cad_and_dirty_git():
    result = PreflightGate().evaluate(
        PreflightInput(False, True, "reconstructed", "accepted", "open", "fresh")
    )
    assert result.status is PreflightStatus.BLOCK
    assert any("git target is dirty" in reason for reason in result.reasons)
    assert any("CAD status" in reason for reason in result.reasons)


def test_goal_cannot_build_without_preflight():
    goal = FaberGoal("g1", "Improve Code memory", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254")
    ledger = GoalLedger()
    proposed = ledger.transition(goal, GoalState.PROPOSED)
    with pytest.raises(PermissionError):
        ledger.transition(proposed, GoalState.APPROVED)


def test_goal_lifecycle_requires_evidence_and_review():
    ledger = GoalLedger()
    preflight = passing_preflight()
    goal = FaberGoal("g1", "Improve Code memory", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254")
    for target in (GoalState.PROPOSED, GoalState.APPROVED, GoalState.PLANNED, GoalState.BUILDING):
        goal = ledger.transition(goal, target, preflight=preflight)
    with pytest.raises(ValueError):
        ledger.transition(goal, GoalState.VERIFIED, preflight=preflight)
    goal = ledger.transition(goal, GoalState.VERIFIED, preflight=preflight, evidence={"tests": "11 passed"})
    with pytest.raises(PermissionError):
        ledger.transition(goal, GoalState.LANDED, review=ReviewVerdict.PENDING)
    goal = ledger.transition(
        goal,
        GoalState.LANDED,
        review=ReviewVerdict.PASS,
        review_evidence=ReviewEvidence(ReviewVerdict.PASS, "diff-g1", "sol"),
        landing_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer"),
    )
    assert goal.state is GoalState.LANDED


def test_definition_of_done_requires_all_postcommit_evidence():
    dod = DefinitionOfDone()
    incomplete = LandingEvidence("sha", ReviewVerdict.PASS, "tests", "", "", "rollback", "", "")
    ok, missing = dod.evaluate(incomplete)
    assert not ok
    assert set(missing) == {"commit_closer", "readback", "runtime_smoke", "brain_change_log", "selfstate"}
    complete = LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer")
    assert dod.evaluate(complete) == (True, ())


def test_blocked_goal_emits_faber_handoff_and_resumes_only_at_checkpoint():
    ledger = GoalLedger()
    preflight = passing_preflight()
    goal = FaberGoal("g1", "Improve Code memory", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254")
    goal = ledger.transition(goal, GoalState.PROPOSED)
    goal = ledger.transition(goal, GoalState.APPROVED, preflight=preflight)
    blocked = ledger.transition(
        goal,
        GoalState.BLOCKED,
        evidence={"blocker": "Sol review BLOCK", "next_step": "fix reviewer findings"},
    )
    handoff = ledger.handoff(blocked, required_gate="gpt-sol-review")
    assert handoff.owner == "faber"
    assert handoff.blocked_from is GoalState.APPROVED
    assert handoff.next_step == "fix reviewer findings"
    resumed = ledger.transition(blocked, GoalState.APPROVED, preflight=preflight)
    assert resumed.state is GoalState.APPROVED
    with pytest.raises(ValueError):
        ledger.transition(blocked, GoalState.PLANNED, preflight=preflight)


def test_handoff_store_survives_next_job_boundary(tmp_path):
    ledger = GoalLedger()
    goal = ledger.transition(FaberGoal("g1", "continue"), GoalState.PROPOSED)
    blocked = ledger.transition(goal, GoalState.BLOCKED, evidence={"blocker": "gate", "next_step": "review"})
    handoff = ledger.handoff(blocked, required_gate="reviewer")
    store = HandoffStore(tmp_path / "faber-handoff.json")
    store.save(handoff)
    loaded = store.load()
    assert loaded == handoff


def test_governed_runner_blocks_at_review_and_returns_handoff():
    preflight = passing_preflight()
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: {"tests": "pass"},
        review=lambda evidence: ReviewVerdict.BLOCK,
        landing=lambda evidence: (_ for _ in ()).throw(AssertionError("must not land")),
    )
    assert result.goal.state is GoalState.BLOCKED
    assert result.handoff is not None
    assert result.handoff.required_gate == "reviewer"


def test_governed_runner_reaches_landed_only_with_complete_evidence():
    preflight = passing_preflight()
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: {"tests": "pass", "diff_id": "diff-g1"},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-g1", "sol"),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer"),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer"),
    )
    assert result.goal.state is GoalState.LANDED


def test_faber_goal_registry_persists_and_selects_operational_goals(tmp_path):
    path = tmp_path / "faber-goals.json"
    registry = FaberGoalRegistry(path)
    goal = FaberGoal("g1", "runtime goal")
    registry.put(goal)
    assert registry.next_operational_goal() == goal
    loaded = FaberGoalRegistry(path)
    assert loaded.get("g1") == goal
    with pytest.raises(ValueError):
        loaded.put(FaberGoal("bad", "wrong", owner="planner"))


def test_reviewer_must_match_current_diff_before_landing():
    preflight = passing_preflight()
    base = dict(tests="pass", diff_id="diff-current")
    mismatch = GovernedCodeRunner().run(
        FaberGoal("g-diff-1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: base,
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-old", "sol"),
        landing=lambda evidence: (_ for _ in ()).throw(AssertionError("must not land")),
    )
    assert mismatch.goal.state is GoalState.BLOCKED
    assert "diff mismatch" in mismatch.blocker

    matched = GovernedCodeRunner().run(
        FaberGoal("g-diff-2", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: base,
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-current", "sol"),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer"),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer"),
    )
    assert matched.goal.state is GoalState.LANDED
