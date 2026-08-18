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
                "lease": "agent/target.py",
                "cad": "CAD-M",
                "adr": "ADR-038",
                "bl": "BL-3254",
                "obsidian": "Brain/Change Log.md",
            },
        )
    )


def test_preflight_blocks_dirty_git_and_missing_refs_not_cad():
    # ADR-062 V4 / BL-4029 L4: preflight er kollisjons- og scope-kontroll.
    # CAD/ADR sjekkes paa steg 7 (DesignGate) — en preflight som krever
    # nedstroems-artefakter er sirkulaer (BL-3673).
    result = PreflightGate().evaluate(
        PreflightInput(False, True, "reconstructed", "accepted", "open", "fresh")
    )
    assert result.status is PreflightStatus.BLOCK
    assert any("git target is dirty" in reason for reason in result.reasons)
    assert any("missing authoritative source refs" in reason for reason in result.reasons)
    assert not any("CAD" in reason for reason in result.reasons)


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
        # steg 8: umaalt blast-radius blokkerer, saa bygget MAA rapportere tall
        build=lambda: {"tests": "pass", "diff_id": "diff-g1",
                       "changed_files": 1, "changed_lines": 10},
        review=lambda evidence: ReviewEvidence(
            ReviewVerdict.BLOCK, "diff-g1", "sol", confidence=0.95),
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
        build=lambda: {"tests": "pass", "diff_id": "diff-g1",
                       "changed_files": 1, "changed_lines": 10},
        # confidence er satt: umaalt konfidens er en second opinion-utloeser
        review=lambda evidence: ReviewEvidence(
            ReviewVerdict.PASS, "diff-g1", "sol", confidence=0.95),
        prelanding_evidence=LandingEvidence(
            "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
            "log", "state", "closer", landing_set=("agent/target.py",)),
        landing=lambda evidence: LandingEvidence(
            "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
            "log", "state", "closer", landing_set=("agent/target.py",)),
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
    base = dict(tests="pass", diff_id="diff-current",
                changed_files=1, changed_lines=10)
    mismatch = GovernedCodeRunner().run(
        FaberGoal("g-diff-1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: base,
        review=lambda evidence: ReviewEvidence(
            ReviewVerdict.PASS, "diff-old", "sol", confidence=0.95),
        landing=lambda evidence: (_ for _ in ()).throw(AssertionError("must not land")),
    )
    assert mismatch.goal.state is GoalState.BLOCKED
    assert "diff mismatch" in mismatch.blocker

    matched = GovernedCodeRunner().run(
        FaberGoal("g-diff-2", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: base,
        review=lambda evidence: ReviewEvidence(
            ReviewVerdict.PASS, "diff-current", "sol", confidence=0.95),
        prelanding_evidence=LandingEvidence(
            "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
            "log", "state", "closer", landing_set=("agent/target.py",)),
        landing=lambda evidence: LandingEvidence(
            "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
            "log", "state", "closer", landing_set=("agent/target.py",)),
    )
    assert matched.goal.state is GoalState.LANDED


# ===== BL-4055 steg 10b: second opinion (reimplementert 2026-08-18, Faber) =====

from agent.second_opinion import SecondOpinionOutcome


def _run_with_opinion(opinion_callable, *, files=("agent/target.py",),
                      confidence=0.95, lease="agent/target.py"):
    preflight = PreflightGate().evaluate(
        PreflightInput(
            git_clean=True, lease_clear=True, cad_status="verified",
            adr_status="accepted", bl_status="open", obsidian_status="fresh",
            source_refs={"git": "HEAD:t", "lease": lease, "bl": "BL-3254", "cad": "CAD-M", "adr": "ADR-038"},
        )
    )
    landing_ev = LandingEvidence(
        "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
        "log", "state", "closer", landing_set=files)
    return GovernedCodeRunner(second_opinion=opinion_callable).run(
        FaberGoal("g-so", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: {"tests": "pass", "diff_id": "d1",
                       "changed_files": 1, "changed_lines": 10, "diff": "diff"},
        review=lambda evidence: ReviewEvidence(
            ReviewVerdict.PASS, "d1", "sol", confidence=confidence),
        prelanding_evidence=landing_ev,
        landing=lambda evidence: landing_ev,
    )


def test_governance_surface_triggers_second_opinion_even_at_high_confidence():
    # «En second opinion som bare paakalles naar man er i tvil, kalles aldri
    # naar man tar feil med selvtillit» — governance-flaten fyrer paa 0.95.
    calls = []
    def agree(change, *, trigger_reasons, diff_text):
        calls.append(trigger_reasons)
        return SecondOpinionOutcome.agree("claude-opus-5")
    result = _run_with_opinion(
        agree, files=("agent/second_opinion.py",), lease="agent/second_opinion.py")
    assert result.goal.state is GoalState.LANDED
    assert calls and any("governance_surface" in r for r in calls[0])
    # BEGGE stemmer loggfoert — ogsaa ved enighet
    assert result.goal.evidence.get("second_opinion_status") == "agree"


def test_second_opinion_dissent_blocks_with_both_votes():
    def dissent(change, *, trigger_reasons, diff_text):
        return SecondOpinionOutcome.dissent(
            "claude-opus-5", reasons=("rollback path untested",))
    result = _run_with_opinion(dissent, confidence=None)  # umaalt = utloeser
    assert result.goal.state is GoalState.BLOCKED
    assert "dissent" in result.blocker
    assert result.handoff is not None


def test_unavailable_second_opinion_blocks_never_skips(monkeypatch):
    # None-klient betyr «bruk den ekte» — runneren ruter til den sene importen.
    # Klienten patches til utilgjengelig saa testen ALDRI gaar paa nett
    # (foerste versjon gjorde et ekte API-kall her — 21 s og et live-svar).
    import agent.second_opinion_client as so_client
    monkeypatch.setattr(
        so_client, "fetch_second_opinion",
        lambda change, *, trigger_reasons, diff_text: SecondOpinionOutcome.unavailable(
            "second opinion client unavailable: test-stub"))
    result = _run_with_opinion(None, confidence=None)
    assert result.goal.state is GoalState.BLOCKED
    assert "unavailable" in result.blocker


def test_agree_without_verified_model_degrades_to_unavailable():
    # En enighet uten API-ekkoet modell-id er en paastand, ikke en enighet.
    def hollow(change, *, trigger_reasons, diff_text):
        return SecondOpinionOutcome.agree("")
    result = _run_with_opinion(hollow, confidence=None)
    assert result.goal.state is GoalState.BLOCKED
