import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from pathlib import Path

import agent.code_workflow as cw
from agent.code_workflow import (
    ScopeBudget,
    LandingScopeGate,
    PreflightResult,

    BlGate,
    DesignGate,
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
    PostcommitLoop,
    ScopeBudget,
    SecretPolicy,
    StepJournal,
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
                # BL-4029: lease-refen NAVNGIR filene, fordi landingssettet maa kunne
                # sammenlignes mot dem ved commit (ADR-062 V4 sjekk 2).
                "lease": "a.py,b.py",
                "cad": "CAD-M",
                "adr": "ADR-038",
                "bl": "BL-3254",
                "obsidian": "Brain/Change Log.md",
            },
        )
    )


def test_preflight_blocks_dirty_git_but_no_longer_judges_design():
    """BL-4029 L4: step 4 keeps collision control and drops design certification.

    The old version of this test asserted that a reconstructed CAD blocks at
    step 4. That is what made the gate impossible: CAD is authored at step 7.
    """
    result = PreflightGate().evaluate(
        PreflightInput(False, True, "reconstructed", "accepted", "open", "fresh")
    )
    assert result.status is PreflightStatus.BLOCK
    assert any("git target is dirty" in reason for reason in result.reasons)
    assert not any("CAD status" in reason for reason in result.reasons), \
        "step 4 must not judge CAD -- that is step 7's job (DesignGate)"


def test_preflight_passes_when_collision_control_is_satisfied():
    """The falsifier BL-4003 could not answer: does a legitimate sequence exist?

    Under the old gate the answer was no for every input, because CAD/ADR/BL/
    Brain are produced later than step 4. Under the relocated contract a goal
    that has done exactly what step 4 can ask -- claimed a lease, kept the
    leased files clean, and targets a scope this host can execute -- passes.
    """
    result = PreflightGate().evaluate(
        PreflightInput(
            git_clean=True, lease_clear=True,
            cad_status="unknown", adr_status="unknown",
            bl_status="reserved", obsidian_status="unknown",
            source_refs={"git": "hermes-agent", "lease": "lease-1"},
        )
    )
    assert result.status is PreflightStatus.PASS, result.reasons


def test_preflight_blocks_when_scope_is_not_executable_here():
    """Measured 2026-08-10: 5 of 7 goals carry AGI scope, and the AGI codebase
    does not exist on .15. Without this they fail at step 8 or later."""
    result = PreflightGate().evaluate(
        PreflightInput(
            git_clean=True, lease_clear=True,
            cad_status="fresh", adr_status="accepted",
            bl_status="open", obsidian_status="fresh",
            source_refs={"git": "x", "lease": "y"},
            scope_executable=False, scope_note="AGI codebase absent on this host",
        )
    )
    assert result.status is PreflightStatus.BLOCK
    assert any("not executable on this host" in r for r in result.reasons)
    assert any("AGI codebase absent" in r for r in result.reasons)


def test_bl_gate_still_refuses_a_reserved_number():
    """BL-3673 (cab10c5f9) must survive the relocation.

    A reserved number means a number was handed out, not that work exists.
    Promoting it to open to get through is writing a record to open a gate --
    the defect reviewer caught on 2026-08-04. Moving the check to step 5 must
    not soften it.
    """
    ev = PreflightInput(True, True, "fresh", "accepted", "reserved", "fresh",
                        source_refs={"bl": "BL-3633"})
    result = BlGate().evaluate(ev)
    assert result.status is PreflightStatus.BLOCK
    assert any("BL status is not actionable: reserved" in r for r in result.reasons)


def test_bl_gate_accepts_an_actual_work_item():
    ev = PreflightInput(True, True, "fresh", "accepted", "in_progress", "fresh",
                        source_refs={"bl": "BL-4029"})
    assert BlGate().evaluate(ev).status is PreflightStatus.PASS


def test_design_gate_still_blocks_a_reconstructed_cad():
    """The check the old preflight made -- relocated, not deleted."""
    ev = PreflightInput(True, True, "reconstructed", "accepted", "open", "fresh",
                        source_refs={"cad": "CAD-1", "adr": "ADR-062"})
    result = DesignGate().evaluate(ev)
    assert result.status is PreflightStatus.BLOCK
    assert any("CAD status is not fresh/verified" in r for r in result.reasons)


def test_design_gate_blocks_an_unaccepted_adr():
    ev = PreflightInput(True, True, "fresh", "proposed", "open", "fresh",
                        source_refs={"cad": "CAD-1", "adr": "ADR-9"})
    assert DesignGate().evaluate(ev).status is PreflightStatus.BLOCK


def _pf(*, bl="in_progress", cad="fresh", adr="accepted"):
    """A step-4 PASS, so the runner is exercised past preflight."""
    ev = PreflightInput(
        git_clean=True, lease_clear=True,
        cad_status=cad, adr_status=adr, bl_status=bl, obsidian_status="fresh",
        source_refs={"git": "g", "lease": "l", "cad": "CAD-1", "adr": "ADR-062", "bl": "BL-1"},
    )
    return PreflightResult(PreflightStatus.PASS, (), ev)


def _never(*_a, **_k):
    raise AssertionError("must not be reached — the gate should have blocked first")


def test_runner_BLOCKS_on_bl_gate_end_to_end():
    """Drives the ENFORCED path, which no structural test can reach.

    The AST guard proves BlGate is CONSTRUCTED. It cannot see a verdict that is
    computed and then thrown away — construct the gate, drop the `if`, and every
    structural test still passes while nothing is enforced. That neutering was
    demonstrated on this very change. Only driving the runner catches it.
    """
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-3633"),
        preflight=_pf(bl="reserved"),
        build=_never, review=_never, landing=_never,
    )
    assert result.goal.state is GoalState.BLOCKED
    assert result.handoff is not None
    assert result.handoff.required_gate == "bl_gate"
    assert "BL status is not actionable: reserved" in result.blocker


def test_runner_BLOCKS_on_design_gate_end_to_end():
    """Same, for step 7. A reconstructed CAD must stop the run before BUILDING."""
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-4029"),
        preflight=_pf(cad="reconstructed"),
        build=_never, review=_never, landing=_never,
    )
    assert result.goal.state is GoalState.BLOCKED
    assert result.handoff is not None
    assert result.handoff.required_gate == "design_gate"
    assert "CAD status is not fresh/verified" in result.blocker


def test_relocated_gates_are_actually_INVOKED_by_the_runner():
    """THE guard the first attempt at L4 was missing.

    ``test_no_check_was_lost_in_the_relocation`` instantiates the gate classes
    directly and asks "does some gate reject this?". The claim, though, is "no
    check was lost FROM ENFORCEMENT" -- a different set. The first version of
    L4 moved four checks into classes with ZERO call sites: every test passed
    while production silently stopped checking BL, CAD and ADR.

    A class-level union test can never discharge a claim about the enforced
    path. This one reads the call graph instead: does ``GovernedCodeRunner.run``
    actually construct both gates?

    Same shape as BL-4006's import-direction guard: a structural assertion
    catches outright REMOVAL, which is the regression that actually happened.

    LIMIT, stated because the next reader will otherwise over-trust it: this
    proves CONSTRUCTION inside ``run``, not ENFORCEMENT. Compute the verdict and
    discard it, and this test still passes. The behavioural pair above
    (``test_runner_BLOCKS_on_*_end_to_end``) is what discharges the claim; keep
    both -- neither alone covers the other's blind spot.
    """
    import ast

    src = Path(cw.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    runner = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.ClassDef) and n.name == "GovernedCodeRunner"), None)
    assert runner is not None, "GovernedCodeRunner not found — the guard is not guarding"

    run_fn = next((n for n in runner.body
                   if isinstance(n, ast.FunctionDef) and n.name == "run"), None)
    assert run_fn is not None, "GovernedCodeRunner.run not found — the guard is not guarding"
    called = {
        n.func.id for n in ast.walk(run_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    # BL-4055: `SecondOpinionTrigger` staar her av noeyaktig samme grunn som de
    # to andre -- vakten finnes for aa fange en gate som defineres uten
    # kallested, og andre-meningen er den nyeste kandidaten til den defekten.
    for gate in ("BlGate", "DesignGate", "SecondOpinionTrigger"):
        assert gate in called, (
            f"{gate} is defined but never constructed by GovernedCodeRunner — "
            f"the check was moved out of enforcement, not into a new phase"
        )


def test_no_check_was_lost_in_the_relocation():
    """THE completeness guard for BL-4029 L4.

    Relocating checks is how a regression gets laundered: move a check, forget
    to land it at the far end, and every test still passes because each gate
    is only asked about its own concerns. This asserts the UNION.

    Every condition the pre-L4 preflight rejected must still be rejected by
    SOME gate. Brain/Obsidian is the one deliberate exception -- CLAUDE.md puts
    it under ETTER, so it belongs to step 13 (DefinitionOfDone), never to an
    entry condition.
    """
    bad = PreflightInput(
        git_clean=False, lease_clear=False,
        cad_status="reconstructed", adr_status="proposed",
        bl_status="reserved", obsidian_status="unknown",
        source_refs={},
    )
    union = " | ".join(
        r for gate in (PreflightGate(), BlGate(), DesignGate())
        for r in gate.evaluate(bad).reasons
    )
    for fragment in ("git target is dirty", "target lease is not clear",
                     "CAD status", "ADR status", "BL status"):
        assert fragment in union, f"{fragment!r} is rejected by NO gate after L4"


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
        landing_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer", landing_set=("a.py",)),
    )
    assert goal.state is GoalState.LANDED


def test_definition_of_done_requires_all_postcommit_evidence():
    dod = DefinitionOfDone()
    incomplete = LandingEvidence("sha", ReviewVerdict.PASS, "tests", "", "", "rollback", "", "")
    ok, missing = dod.evaluate(incomplete)
    assert not ok
    assert set(missing) == {"commit_closer", "readback", "runtime_smoke", "brain_change_log", "selfstate"}
    complete = LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer", landing_set=("a.py",))
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


def _concurring_second_opinion(change, **_):
    """BL-4055: en UAVHENGIG vurderer som er enig.

    Injiseres eksplisitt i landings-testene under. Poenget med aa skrive den ut
    i stedet for aa la den ekte klienten svare, er at en test som LANDER naa maa
    vise begge stemmene -- en landing er ikke lenger én vurderers avgjoerelse.
    """
    from agent.second_opinion import SecondOpinionOutcome, SecondOpinionStatus

    return SecondOpinionOutcome(
        status=SecondOpinionStatus.CONCUR, reason="independently checked",
        provenance="anthropic.api", model="claude-opus-5", confidence=0.9)


def test_governed_runner_blocks_at_review_and_returns_handoff():
    preflight = passing_preflight()
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: {"tests": "pass", "changed_files": 1, "changed_lines": 5},
        review=lambda evidence: ReviewVerdict.BLOCK,
        landing=lambda evidence: (_ for _ in ()).throw(AssertionError("must not land")),
    )
    assert result.goal.state is GoalState.BLOCKED
    assert result.handoff is not None
    assert result.handoff.required_gate == "reviewer"


def test_governed_runner_reaches_landed_only_with_complete_evidence():
    preflight = passing_preflight()
    result = GovernedCodeRunner(second_opinion=_concurring_second_opinion).run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: {"tests": "pass", "diff_id": "diff-g1", "changed_files": 2,
                       "changed_lines": 40, "diff": "--- a\n+++ b\n+x"},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-g1", "sol",
                                               confidence=0.95),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer", landing_set=("a.py",)),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer", landing_set=("a.py",)),
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
    base = dict(tests="pass", diff_id="diff-current", changed_files=1,
                changed_lines=8, diff="--- a\n+++ b\n+x")
    mismatch = GovernedCodeRunner().run(
        FaberGoal("g-diff-1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: base,
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-old", "sol"),
        landing=lambda evidence: (_ for _ in ()).throw(AssertionError("must not land")),
    )
    assert mismatch.goal.state is GoalState.BLOCKED
    assert "diff mismatch" in mismatch.blocker

    matched = GovernedCodeRunner(second_opinion=_concurring_second_opinion).run(
        FaberGoal("g-diff-2", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: base,
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-current", "sol",
                                               confidence=0.95),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer", landing_set=("a.py",)),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback", "log", "state", "closer", landing_set=("a.py",)),
    )
    assert matched.goal.state is GoalState.LANDED


def test_postcommit_loop_requires_all_evidence_and_persists_readback(tmp_path):
    loop = PostcommitLoop(readback_path=tmp_path / "postcommit.json")
    result = loop.run(
        commit="sha",
        reviewer=ReviewVerdict.PASS,
        tests=lambda: "tests-pass",
        commit_closer=lambda _: "closer-ok",
        brain_change_log=lambda _: "brain-ok",
        selfstate=lambda _: "selfstate-ok",
        readback=lambda _: "readback-ok",
        runtime_smoke=lambda _: "smoke-ok",
        rollback=lambda _: "rollback-ok",
    )
    assert result.success
    assert (tmp_path / "postcommit.json").exists()

    blocked = PostcommitLoop().run(
        commit="sha",
        reviewer=ReviewVerdict.PASS,
        tests=lambda: "tests-pass",
        commit_closer=lambda _: "",
        brain_change_log=lambda _: "brain-ok",
        selfstate=lambda _: "selfstate-ok",
        readback=lambda _: "readback-ok",
        runtime_smoke=lambda _: "smoke-ok",
        rollback=lambda _: "rollback-ok",
    )
    assert not blocked.success
    assert blocked.missing == ("commit_closer",)


def test_goal_ledger_persists_transition_history(tmp_path):
    ledger = GoalLedger(tmp_path / "goal-history.json")
    goal = FaberGoal("history", "goal", cad_ref="CAD-M", adr_ref="ADR-042", bl_ref="BL-3589")
    proposed = ledger.transition(goal, GoalState.PROPOSED)
    assert proposed.state is GoalState.PROPOSED
    history = json.loads((tmp_path / "goal-history.json").read_text())
    assert history[-1]["from"] == "candidate"
    assert history[-1]["to"] == "proposed"


def test_scope_budget_blocks_blast_radius():
    ok, reasons = ScopeBudget().evaluate(changed_files=11, changed_lines=501)
    assert not ok
    assert "files>10" in reasons[0]
    assert "lines>500" in reasons[1]


def test_secret_policy_blocks_credentials_and_allows_normal_evidence():
    assert SecretPolicy.violations("commit=abc tests=143") == ()
    with pytest.raises(PermissionError, match="secrets policy BLOCK"):
        SecretPolicy.assert_safe("api_key=super-secret-value")


def test_step_journal_is_idempotent_and_atomic(tmp_path):
    journal = StepJournal(tmp_path / "steps.json")
    first = journal.complete("trace:step", result={"evidence": "ok"})
    second = journal.complete("trace:step", result={"evidence": "different"})
    assert first["status"] == "DONE"
    assert second["status"] == "ALREADY_DONE"
    assert second["result"] == {"evidence": "ok"}


def test_step_journal_preserves_concurrent_distinct_completions(tmp_path):
    journal = StepJournal(tmp_path / "steps.json")

    def complete(index):
        return journal.complete(f"trace:step:{index}", result={"evidence": str(index)})

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = tuple(pool.map(complete, range(8)))

    assert all(record["status"] == "DONE" for record in records)
    persisted = json.loads((tmp_path / "steps.json").read_text())
    assert set(persisted) == {f"trace:step:{index}" for index in range(8)}


def test_postcommit_loop_reuses_completed_steps(tmp_path):
    calls = []
    journal = StepJournal(tmp_path / "steps.json")

    def evidence(name):
        def callback(*_):
            calls.append(name)
            return name
        return callback

    kwargs: dict[str, Any] = dict(
        commit="sha",
        reviewer=ReviewVerdict.PASS,
        tests=evidence("tests"),
        commit_closer=evidence("commit_closer"),
        brain_change_log=evidence("brain_change_log"),
        selfstate=evidence("selfstate"),
        readback=evidence("readback"),
        runtime_smoke=evidence("runtime_smoke"),
        rollback=evidence("rollback"),
    )
    first = PostcommitLoop(journal=journal).run(**kwargs)
    calls_after_first = list(calls)
    second = PostcommitLoop(journal=journal).run(**kwargs)
    assert first.success and second.success

    # BL-4029 A3: this assertion used to be `calls_after_first == calls`, i.e.
    # the second run re-executed NOTHING. That is idempotency for steps which
    # RECORD something -- and a hole for steps which PROVE something: anyone
    # able to write the journal made postcommit report DONE without tests or a
    # runtime smoke ever running. Recording steps still replay; proving steps
    # are re-verified every time.
    #
    # BL-4052 CORRECTS the classification above without changing its principle.
    # A3 put `readback` and `rollback` in the replay set, but both PROVE rather
    # than RECORD: readback asserts the commit still contains exactly what it
    # should, and rollback asserts the revert still applies. Replaying either
    # means a journal write makes the assertion report DONE without anything
    # being read or checked -- which is the very hole A3 closed for tests and
    # runtime_smoke, left open two slots further along. Now all four re-verify.
    new_calls = calls[len(calls_after_first):]
    assert set(new_calls) == {"tests", "runtime_smoke", "readback", "rollback"}, new_calls
    assert "commit_closer" not in new_calls
    assert set(second.replayed) == {"commit_closer", "brain_change_log", "selfstate"}
    assert set(second.executed) == {"tests", "runtime_smoke", "readback", "rollback"}


# --------------------------------------------------------- BL-4029: Part A ---

def test_secret_policy_fires_on_json_which_is_how_it_is_actually_called():
    """The inherited version could not fire where it was used.

    Its only call site serialised to JSON and then applied a regex that
    required `keyword:` with no quote between -- so JSON never matched. The
    gate ran, returned clean, and was structurally incapable of firing on
    anything but a bare PEM header. A control that cannot fail is worse than no
    control, because it gets cited as one.
    """
    import json as _json
    for payload in ({"api_key": "sk-abcdefghijklmnop"},
                    {"password": "hunter2"},
                    {"token": "ghp_aaaaaaaaaaaaaaaaaaaaaa"}):
        blob = _json.dumps(payload)
        assert cw.SecretPolicy.violations(blob), f"must fire on {blob}"


def test_secret_policy_catches_bare_provider_tokens_without_a_keyword():
    for token in ("AKIAIOSFODNN7EXAMPLE", "sk-abcdefghijklmnopqrst",
                  "ghp_aaaaaaaaaaaaaaaaaaaaaaaa"):
        assert cw.SecretPolicy.violations(f"value is {token}"), token


def test_secret_policy_does_not_cry_wolf_on_ordinary_evidence():
    """A negative gate nobody trusts is a negative gate nobody keeps."""
    assert not cw.SecretPolicy.structural_violations({"tests": "17 passed", "commit": "abc123"})
    assert not cw.SecretPolicy.violations("17 passed in 0.34s")


def test_secret_policy_walks_structure_before_serialising():
    """Encoding-independent: a check that depends on the encoder is a check a
    different encoder silently disables."""
    hits = cw.SecretPolicy.structural_violations({"outer": [{"client_secret": "x"}]})
    assert hits and "client_secret" in hits[0]


def test_postcommit_never_replays_a_step_that_PROVES_something(tmp_path):
    """BL-4029 A3. The inherited loop replayed a recorded string for EVERY
    step, including tests and runtime_smoke -- so whoever could write the
    journal made postcommit report DONE without a step running. Replay is fine
    for steps that RECORD; never for steps that PROVE.
    """
    journal = cw.StepJournal(tmp_path / "j.json")
    def cb(name):
        return lambda *a, **k: f"{name}-evidence"
    def run():
        return cw.PostcommitLoop(journal=journal, readback_path=tmp_path / "rb.json").run(
            commit="abc123", reviewer=cw.ReviewVerdict.PASS,
            tests=cb("tests"), commit_closer=cb("commit_closer"),
            brain_change_log=cb("brain_change_log"), selfstate=cb("selfstate"),
            readback=cb("readback"), runtime_smoke=cb("runtime_smoke"),
            rollback=cb("rollback"))

    first = run()
    assert first.success and len(first.executed) == 7

    second = run()
    assert second.success
    assert "tests" in second.executed, "tests must be re-verified, never replayed"
    assert "runtime_smoke" in second.executed, "runtime_smoke must be re-verified"
    assert "commit_closer" in second.replayed, "recording steps may legitimately replay"
    # success must never be ambiguous about whether the work ran
    assert set(second.replayed) & set(second.executed) == set()


# ------------------------------------------- BL-4029 steg 11: landingssettet ---

def test_landing_set_must_be_a_subset_of_the_lease_set():
    """ADR-062 V4 sjekk 2 — den ene mekaniske sjekken som forhindrer sveipet."""
    r = LandingScopeGate().evaluate(["a.py", "b.py"], ["a.py", "b.py", "c.py"])
    assert r.status is PreflightStatus.PASS, r.reasons


def test_landing_fewer_files_than_leased_is_legitimate():
    """Man tar lease FOER man vet hva som trengs. Delmengde, ikke likhet."""
    assert LandingScopeGate().evaluate(["a.py"], ["a.py", "b.py"]).status is PreflightStatus.PASS


def test_the_ae832c8a4_sweep_is_blocked():
    """Skaden CLAUDE.md dokumenterer — og som traff MEG i denne oekten.

    En `git add` av EN fil ble til en commit med 219, fordi indeksen deles mellom
    sesjoner og `git commit` uten stier tar alt som ligger der. Eksplisitt `git add`
    var regelen jeg FULGTE da det skjedde; den er ikke nok.
    """
    leased = ["planning/mitt.md"]
    sweeping = ["planning/mitt.md"] + [f"mwp-uosh/agent/andres_{i}.py" for i in range(218)]
    r = LandingScopeGate().evaluate(sweeping, leased)
    assert r.status is PreflightStatus.BLOCK
    assert any("not a subset" in x for x in r.reasons)
    assert any("andres_0.py" in x for x in r.reasons), "de fremmede filene maa NAVNGIS"


def test_an_empty_landing_set_blocks_because_unknown_is_not_empty():
    """Et ukjent filsett er ikke «trygt fordi det er tomt».

    En ukjent mengde kan ikke vaere en delmengde av noe. Dagens gjennomgaaende
    laerdom, i én gate: fravaer av data er ikke et positivt funn.
    """
    r = LandingScopeGate().evaluate([], ["a.py"])
    assert r.status is PreflightStatus.BLOCK
    assert any("empty or unknown" in x for x in r.reasons)


def test_an_empty_lease_set_blocks():
    r = LandingScopeGate().evaluate(["a.py"], [])
    assert r.status is PreflightStatus.BLOCK
    assert any("lease set is empty" in x for x in r.reasons)


def test_runner_BLOCKS_when_landing_would_leave_the_lease(monkeypatch):
    """Driver den HAANDHEVEDE stien, ikke bare gate-klassen.

    Samme laerdom som L4: en klasse-nivaa-test kan aldri innfri en paastand om den
    haandhevede stien. Her landes en fil som ikke er leaset, gjennom runneren.
    """
    ev = PreflightInput(
        git_clean=True, lease_clear=True, cad_status="fresh", adr_status="accepted",
        bl_status="open", obsidian_status="fresh",
        source_refs={"git": "g", "lease": "a.py", "cad": "C", "adr": "A", "bl": "B"},
    )
    landing = LandingEvidence(
        landing_set=("a.py", "IKKE_LEASET.py"),
        commit="sha", reviewer=ReviewVerdict.PASS, tests="ok", readback="ok",
        runtime_smoke="ok", rollback="ok", brain_change_log="ok", selfstate="ok",
        commit_closer="ok",
    )
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="C", adr_ref="A", bl_ref="B"),
        preflight=PreflightResult(PreflightStatus.PASS, (), ev),
        build=lambda: {"tests": "ok", "diff_id": "d1", "changed_files": 1, "changed_lines": 10},
        review=lambda e: ReviewEvidence(verdict=ReviewVerdict.PASS, diff_id="d1", reviewer="r"),
        landing=lambda e: landing,
        prelanding_evidence=landing,
    )
    assert result.goal.state is GoalState.BLOCKED
    assert result.handoff.required_gate == "landing_scope"
    assert "IKKE_LEASET.py" in result.blocker


# ---------------------------------------------- BL-4029 steg 8: blast-radius ---

def _pf_ok():
    ev = PreflightInput(
        git_clean=True, lease_clear=True, cad_status="fresh", adr_status="accepted",
        bl_status="open", obsidian_status="fresh",
        source_refs={"git": "g", "lease": "a.py", "cad": "C", "adr": "A", "bl": "B"})
    return PreflightResult(PreflightStatus.PASS, (), ev)


def _run_with_build(build_result):
    return GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="C", adr_ref="A", bl_ref="B"),
        preflight=_pf_ok(),
        build=lambda: build_result,
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "d1", "r"),
        landing=lambda e: None,
        prelanding_evidence=None,
    )


def test_build_that_does_not_report_its_blast_radius_is_BLOCKED():
    """UMAALT er ikke "liten".

    En build som ikke sier hvor mye den endret, kan ikke vises aa vaere innenfor et
    budsjett. Samme regel som tomt landingssett paa steg 11, og samme gjennomgaaende
    laerdom: fravaer av data er ikke et positivt funn.
    """
    r = _run_with_build({"tests": "pass", "diff_id": "d1"})
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "scope_budget"
    assert "changed_files" in r.blocker and "changed_lines" in r.blocker


def test_build_within_budget_passes_step_8():
    r = _run_with_build({"tests": "pass", "diff_id": "d1",
                         "changed_files": 3, "changed_lines": 120})
    # Gaar videre forbi steg 8; stopper senere paa manglende landings-evidens.
    assert r.handoff is None or r.handoff.required_gate != "scope_budget"


def test_a_change_too_large_to_review_properly_is_BLOCKED():
    """Grensen er ikke moralsk, den er praktisk.

    En patch paa 40 filer kan ikke reviewes ordentlig, og en reviewer som ikke KAN
    se hele endringen gir en PASS som ikke betyr det den ser ut til aa bety. Steg 10
    er bare saa sterk som stoerrelsen paa det den faar se.
    """
    r = _run_with_build({"tests": "pass", "diff_id": "d1",
                         "changed_files": 40, "changed_lines": 9000})
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "scope_budget"
    assert "files>" in r.blocker and "lines>" in r.blocker


def test_non_numeric_metrics_are_BLOCKED_not_coerced():
    r = _run_with_build({"tests": "pass", "diff_id": "d1",
                         "changed_files": "mange", "changed_lines": 10})
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "scope_budget"


def test_a_runner_always_has_a_budget():
    """Ingen budsjett ville stilltiende gjenopprettet tilstanden foer L4:
    ScopeBudget definert, men aldri spurt."""
    assert GovernedCodeRunner().scope_budget is not None
    assert GovernedCodeRunner(scope_budget=ScopeBudget(max_files=1)).scope_budget.max_files == 1


# ===========================================================================
# BL-4052 — steg 12 (runtime_smoke) og steg 13 (postcommit_readback)
# ===========================================================================

from agent.code_workflow import (  # noqa: E402
    BindMount,
    CommitReadback,
    ContainerRuntimeTarget,
    PostcommitReadbackGate,
    RetiredFleetGate,
    RuntimeProbe,
    RuntimeSmokeGate,
    StepBlocked,
)


def _blocks(result):
    return result.status is cw.PreflightStatus.BLOCK


def _reason(result):
    return " | ".join(result.reasons)


# --- den maalte virkeligheten paa .12, brukt som fixture ------------------
# docker inspect efc-unified-api, 2026-08-11. Vertsfila er synlig TO steder
# inne i containeren samtidig, og WorkingDir avgjoer hvilken som importeres.
EFC_UNIFIED_API = ContainerRuntimeTarget(
    name="efc-unified-api",
    working_dir="/repo",
    cmd=("uvicorn", "apis.unified_api.main:app", "--host", "0.0.0.0", "--port", "8080"),
    mounts=(
        BindMount("/home/byopus/AGI", "/repo"),
        BindMount("/home/byopus/AGI/apis/unified_api/main.py", "/app/apis/unified_api/main.py"),
        BindMount("/home/byopus/AGI/symbiose", "/app/symbiose"),
        BindMount("/home/byopus/AGI/certs/pa-ssl-ca.crt", "/certs/pa-ssl-ca.crt"),
    ),
)


def fresh_probe(**over):
    """En probe der ALT er maalt og alt stemmer."""
    base = dict(
        target="efc-unified-api",
        answered=True,
        running=True,
        started_at="2026-08-10T19:07:07.602127692Z",   # UTC
        loaded_path="/repo/apis/unified_api/main.py",
        observed_digest="97d8ede366b16b3117adee823bad8952",
        expected_digest="97d8ede366b16b3117adee823bad8952",
        source_mtime="2026-08-10T18:17:35.934017+00:00",  # foer prosessstart
        probe_method="docker exec",
    )
    base.update(over)
    return RuntimeProbe(**base)


# --- steg 12: hovedregelen ------------------------------------------------

def test_step12_a_probe_that_got_no_answer_is_not_a_pass():
    """Dagens gjennomgaaende regel, i sin reneste form."""
    result = RuntimeSmokeGate().evaluate(
        RuntimeProbe(target="efc-unified-api", answered=False,
                     probe_method="docker exec", note="container not found"))

    assert _blocks(result)
    assert "not answered is not a passed smoke test" in _reason(result)
    assert "container not found" in _reason(result)


def test_step12_a_fully_measured_and_consistent_probe_passes():
    assert RuntimeSmokeGate().evaluate(fresh_probe()).status is cw.PreflightStatus.PASS


def test_step12_file_newer_than_process_start_blocks():
    """Kjernen i steg 12: oppdatert fil er ikke oppdatert prosess."""
    result = RuntimeSmokeGate().evaluate(fresh_probe(
        started_at="2026-08-10T19:07:07+00:00",
        source_mtime="2026-08-11T09:00:00+00:00",   # skrevet ETTER start
    ))

    assert _blocks(result)
    assert "source is NEWER than the running process" in _reason(result)
    assert "never restarted" in _reason(result)


def test_step12_naive_timestamp_blocks_instead_of_being_assumed_utc():
    """Maalt 2026-08-11: mtime +0200 vs StartedAt UTC. Uten sone snus svaret.

    Den naive strengen "2026-08-10 20:17:35" ser NYERE ut enn UTC-starten
    19:07:07, saa en soneloes sammenligning ville gitt FALSK BLOCK -- den
    faktiske sannheten er at prosessen startet 50 minutter etter skrivingen.
    Gaten nekter aa gjette hvilken av dem det er.
    """
    result = RuntimeSmokeGate().evaluate(fresh_probe(source_mtime="2026-08-10 20:17:35.934017"))

    assert _blocks(result)
    assert "carries no timezone" in _reason(result)
    assert "inverts the verdict" in _reason(result)


def test_step12_same_instant_expressed_in_two_zones_is_not_a_regression():
    """+0200-stempelet er FOER UTC-starten, og skal passere naar sonen er med."""
    result = RuntimeSmokeGate().evaluate(fresh_probe(
        started_at="2026-08-10T19:07:07.602127692Z",
        source_mtime="2026-08-10T20:17:35.934017+02:00",   # = 18:17:35Z
    ))

    assert result.status is cw.PreflightStatus.PASS


def test_step12_only_an_in_process_read_is_an_accepted_probe_method():
    """Maalt: `docker cp` foelger bind-mounten ut til verten (md5 97d8ede3... begge steder).

    Allowlist, ikke svarteliste (reviewer B7). En svarteliste paa et
    SELVRAPPORTERT felt fanger bare kallere som beskriver feilen sin med
    nettopp de ordene listen kjenner -- `docker  cp` med to mellomrom,
    `docker container cp`, `podman cp` og «cat on host» slapp alle gjennom.
    """
    assert RuntimeSmokeGate().evaluate(
        fresh_probe(probe_method="docker exec")).status is cw.PreflightStatus.PASS
    # ...og normalisering av mellomrom/store bokstaver skal ikke aapne den igjen
    assert RuntimeSmokeGate().evaluate(
        fresh_probe(probe_method="  DOCKER   exec ")).status is cw.PreflightStatus.PASS

    for evasion in ("docker cp", "docker  cp", "docker container cp", "podman cp",
                    "kubectl cp", "cat on host", "host file read", "ssh .12 docker cp"):
        result = RuntimeSmokeGate().evaluate(fresh_probe(probe_method=evasion))
        assert _blocks(result), evasion
        assert "not a recognised in-process read" in _reason(result), evasion
        assert "cannot fail" in _reason(result), evasion


def test_step12_unrecorded_probe_method_blocks():
    """Grunnen assereres: uten den overlever mutasjonen som fjerner sjekken.

    Med metoden fjernet faller "" gjennom til allowlist-grenen og blokkerer
    likevel -- men da paa «ikke en gjenkjent in-process-lesing», altsaa en
    paastand om at kalleren oppga en UGYLDIG metode naar sannheten er at den
    ikke oppga noen. Feil begrunnelse er feil funn.
    """
    result = RuntimeSmokeGate().evaluate(fresh_probe(probe_method=""))

    assert _blocks(result)
    assert "was not recorded" in _reason(result)
    assert "not a recognised in-process read" not in _reason(result)


def test_step12_stopped_or_unknown_container_blocks():
    stopped = RuntimeSmokeGate().evaluate(fresh_probe(running=False))
    unknown = RuntimeSmokeGate().evaluate(fresh_probe(running=None))

    assert _blocks(stopped) and "stopped container is not deployed" in _reason(stopped)
    assert _blocks(unknown) and "unknown is not running" in _reason(unknown)


def test_step12_digest_mismatch_blocks():
    result = RuntimeSmokeGate().evaluate(fresh_probe(observed_digest="deadbeefdeadbeef"))

    assert _blocks(result)
    assert "different file than the one landed" in _reason(result)


def test_step12_unmeasured_digest_or_path_blocks():
    """Umaalt er ikke likt. Fravaer av data er ikke et positivt funn.

    Grunnen ASSERTERES, ikke bare at det blokkerer. En mutasjonstest viste
    hvorfor: fjerner man umaalt-sjekken, blokkerer en probe med EN manglende
    digest fortsatt -- men paa "mismatch", altsaa en paastand om at filene er
    ULIKE naar sannheten er at de aldri ble sammenlignet. Og med BEGGE
    manglende blir "" == "", saa den slipper helt gjennom. En test som bare
    spoer «blokkerte den?» kan ikke se forskjell paa de to, og da er vakten
    uovervaaket selv om den finnes.
    """
    for missing in ({"observed_digest": None}, {"expected_digest": None},
                    {"observed_digest": None, "expected_digest": None}):
        result = RuntimeSmokeGate().evaluate(fresh_probe(**missing))
        assert _blocks(result), missing
        assert "digest not measured" in _reason(result), missing
        assert "different file than the one landed" not in _reason(result), missing

    assert _blocks(RuntimeSmokeGate().evaluate(fresh_probe(loaded_path=None)))
    assert _blocks(RuntimeSmokeGate().evaluate(fresh_probe(started_at=None)))
    assert _blocks(RuntimeSmokeGate().evaluate(fresh_probe(source_mtime=None)))


# --- steg 12: mount-analysen ----------------------------------------------

def test_mount_analysis_picks_the_copy_on_syspath_not_the_image_baked_one():
    """Samme vertsfil, to container-stier. WorkingDir=/repo avgjoer."""
    host = "/home/byopus/AGI/apis/unified_api/main.py"

    assert set(EFC_UNIFIED_API.container_paths_for(host)) == {
        "/app/apis/unified_api/main.py",
        "/repo/apis/unified_api/main.py",
    }
    path, why = EFC_UNIFIED_API.resolve_loaded_path(host)
    assert path == "/repo/apis/unified_api/main.py" and why == ""
    assert EFC_UNIFIED_API.import_root() == "/repo"


def test_mount_analysis_blocks_a_file_the_container_cannot_see():
    path, why = EFC_UNIFIED_API.resolve_loaded_path("/home/agent/hermes-agent/agent/x.py")

    assert path is None
    assert "not visible inside" in why


def test_mount_analysis_blocks_a_copy_that_is_not_on_syspath():
    """Fila finnes i containeren, men ikke der prosessen importerer fra."""
    target = ContainerRuntimeTarget(
        name="c", working_dir="/repo",
        mounts=(BindMount("/host/tools", "/app/tools"),))

    path, why = target.resolve_loaded_path("/host/tools/mod.py")

    assert path is None
    assert "sys.path[0]=/repo" in why and "does not import this copy" in why


def test_mount_analysis_blocks_when_the_working_directory_was_not_measured():
    """Docker rapporterer tom WorkingDir for ethvert image uten WORKDIR.

    Reviewer B3: import_root() returnerte da "/", som er prefiks til ALT, saa en
    umaalt arbeidsmappe ble stilltiende til «alt ligger paa sys.path» -- og en
    eneste synlig kopi ble godtatt som «den lastede» uten begrunnelse.
    """
    target = ContainerRuntimeTarget(
        name="c", working_dir="", mounts=(BindMount("/host/tools", "/app/tools"),))

    path, why = target.resolve_loaded_path("/host/tools/mod.py")

    assert target.import_root() == ""
    assert path is None
    assert "no working directory" in why and "unmeasured" in why


def test_mount_analysis_refuses_to_guess_between_two_candidates():
    target = ContainerRuntimeTarget(
        name="c", working_dir="/repo",
        mounts=(BindMount("/host", "/repo"), BindMount("/host/tools", "/repo/tools2")))

    path, why = target.resolve_loaded_path("/host/tools/mod.py")

    assert path is None
    assert "ambiguously" in why


def test_mount_analysis_matches_the_dot12_module_contract():
    """.12 kjoerer `python -u -m tools.<modul>` fra bind-mounten, ikke /app/<fil>.py."""
    target = ContainerRuntimeTarget(
        name="efc-tool", working_dir="/repo",
        cmd=("python", "-u", "-m", "tools.graph_healer"),
        mounts=(BindMount("/home/byopus/AGI/compose/tools", "/repo/tools"),))

    path, why = target.resolve_loaded_path("/home/byopus/AGI/compose/tools/graph_healer.py")

    assert path == "/repo/tools/graph_healer.py" and why == ""


# --- steg 12: ADR-043 ------------------------------------------------------

def test_retired_fleet_gate_blocks_when_the_local_fleet_is_not_empty():
    result = RetiredFleetGate().evaluate(probed=True, container_names=["efc-unified-api"])

    assert _blocks(result)
    assert "ADR-043" in _reason(result)


def test_retired_fleet_gate_blocks_when_it_was_never_probed():
    """Uunder soekt er ikke tomt."""
    result = RetiredFleetGate().evaluate(probed=False)

    assert _blocks(result)
    assert "unprobed is not empty" in _reason(result)


def test_retired_fleet_gate_passes_on_a_measured_empty_fleet():
    assert RetiredFleetGate().evaluate(
        probed=True, container_names=()).status is cw.PreflightStatus.PASS


# --- steg 13 ---------------------------------------------------------------

def good_readback(**over):
    base = dict(commit="a" * 40, resolved=True, reachable_from_head=True,
                files=("agent/code_workflow.py",), subject="BL-4052 steg 12 og 13",
                read_method="git diff-tree")
    base.update(over)
    return CommitReadback(**base)


EXPECTED = ("agent/code_workflow.py",)


def test_step13_a_commit_that_was_not_found_blocks_rather_than_logging():
    result = PostcommitReadbackGate().evaluate(
        CommitReadback(commit="a" * 40, resolved=False), expected_files=EXPECTED)

    assert _blocks(result)
    assert "could not be read back" in _reason(result)
    assert "not a line in a log" in _reason(result)


def test_step13_an_exact_commit_passes():
    result = PostcommitReadbackGate().evaluate(
        good_readback(), expected_files=EXPECTED, require_ref="BL-4052")

    assert result.status is cw.PreflightStatus.PASS


def test_step13_foreign_files_block():
    """Sveipet fra ae832c8a4, fanget etter commit i stedet for foer."""
    result = PostcommitReadbackGate().evaluate(
        good_readback(files=("agent/code_workflow.py", "apps/desktop/electron/main.ts")),
        expected_files=EXPECTED)

    assert _blocks(result)
    assert "never meant to touch" in _reason(result)
    assert "apps/desktop/electron/main.ts" in _reason(result)


def test_step13_a_missing_expected_file_blocks():
    """Noeyaktig, ikke bare 'ingenting fremmed'."""
    result = PostcommitReadbackGate().evaluate(
        good_readback(files=("agent/code_workflow.py",)),
        expected_files=("agent/code_workflow.py", "tests/test_code_workflow.py"))

    assert _blocks(result)
    assert "missing 1 file(s)" in _reason(result)


def test_step13_unknown_and_empty_file_sets_are_different_and_both_block():
    unknown = PostcommitReadbackGate().evaluate(good_readback(files=None), expected_files=EXPECTED)
    empty = PostcommitReadbackGate().evaluate(good_readback(files=()), expected_files=EXPECTED)

    assert _blocks(unknown) and "file set of" in _reason(unknown) and "unknown" in _reason(unknown)
    assert _blocks(empty) and "touches no files" in _reason(empty)


def test_step13_an_unstated_expectation_blocks():
    """En 'noeyaktig'-sjekk uten fasit er en sjekk som ikke kan feile."""
    result = PostcommitReadbackGate().evaluate(good_readback(), expected_files=())

    assert _blocks(result)
    assert "cannot fail is not a check" in _reason(result)


def test_step13_unreachable_or_unmeasured_reachability_blocks():
    orphan = PostcommitReadbackGate().evaluate(
        good_readback(reachable_from_head=False), expected_files=EXPECTED)
    unknown = PostcommitReadbackGate().evaluate(
        good_readback(reachable_from_head=None), expected_files=EXPECTED)

    assert _blocks(orphan) and "sits on no branch" in _reason(orphan)
    assert _blocks(unknown) and "unknown is not reachable" in _reason(unknown)


def test_step13_a_commit_without_its_bl_ref_blocks():
    result = PostcommitReadbackGate().evaluate(
        good_readback(subject="drive-by fix"), expected_files=EXPECTED, require_ref="BL-4052")

    assert _blocks(result)
    assert "does not carry BL-4052" in _reason(result)


# --- integrasjon med PostcommitLoop ---------------------------------------

def _loop_callbacks(**over):
    base = {name: (lambda c, n=name: f"{n} ok") for name in
            ("commit_closer", "brain_change_log", "selfstate", "readback",
             "runtime_smoke", "rollback")}
    base["tests"] = lambda: "tests ok"
    base.update(over)
    return base


def test_postcommit_loop_preserves_a_blocked_step_reason():
    """Tom streng er fail-closed, men stum. Begrunnelsen er verdien."""
    def blocking(_commit):
        raise StepBlocked("runtime_smoke", "source is NEWER than the running process")

    result = PostcommitLoop().run(
        commit="c" * 40, reviewer=ReviewVerdict.PASS,
        **_loop_callbacks(runtime_smoke=blocking))

    assert result.success is False
    assert result.missing == ("runtime_smoke",)
    assert "source is NEWER than the running process" in result.error


def test_postcommit_loop_never_replays_a_step_that_proves_something(tmp_path):
    """Et journalskriv skal ikke kunne gjoere steg 13 til DONE uten aa lese noe."""
    journal = StepJournal(tmp_path / "journal.json")
    sha = "d" * 40
    for name in ("commit_closer", "brain_change_log", "selfstate",
                 "readback", "rollback", "runtime_smoke", "tests"):
        journal.complete(f"postcommit:{sha}:{name}", result={"evidence": "recorded earlier"})

    ran: list[str] = []

    def track(name):
        def call(*_args):
            ran.append(name)
            return f"{name} ok"
        return call

    result = PostcommitLoop(journal=journal).run(
        commit=sha, reviewer=ReviewVerdict.PASS,
        **_loop_callbacks(**{n: track(n) for n in
                             ("readback", "rollback", "runtime_smoke", "commit_closer")},
                          tests=track("tests")))

    assert result.success is True
    # commit_closer only RECORDS, so replay is legitimate; the other four PROVE.
    assert set(result.replayed) == {"commit_closer", "brain_change_log", "selfstate"}
    assert set(ran) == {"readback", "rollback", "runtime_smoke", "tests"}


# --- reviewer runde 2: vakter som fantes men var uovervaaket ---------------

def test_step12_unparseable_timestamp_blocks_with_its_own_reason():
    """R13: den naive grenen var testet, den ULESELIGE var ikke."""
    result = RuntimeSmokeGate().evaluate(fresh_probe(started_at="not-a-timestamp"))

    assert _blocks(result)
    assert "unparseable timestamp" in _reason(result)


def test_mount_analysis_does_not_match_a_sibling_directory_by_prefix():
    """R14: /repofoo ligger ikke under /repo, uansett hvor likt det ser ut."""
    target = ContainerRuntimeTarget(
        name="c", working_dir="/repo", mounts=(BindMount("/host", "/repofoo"),))

    path, why = target.resolve_loaded_path("/host/x.py")

    assert path is None
    assert "/repofoo/x.py" in why and "sys.path[0]=/repo" in why


def test_mount_analysis_handles_a_root_working_directory():
    """D4: WorkingDir="/" ble rstrip-et til "" og feildiagnostisert som umaalt."""
    target = ContainerRuntimeTarget(
        name="c", working_dir="/", mounts=(BindMount("/host/app", "/app"),))

    assert target.import_root() == "/"
    assert target.resolve_loaded_path("/host/app/mod.py") == ("/app/mod.py", "")


def test_step13_a_readback_without_a_sha_blocks():
    """R10."""
    result = PostcommitReadbackGate().evaluate(
        CommitReadback(commit="   ", resolved=True), expected_files=("a.py",))

    assert _blocks(result)
    assert "nothing to read back" in _reason(result)


# ------------------------------------------- BL-4055 steg 10b: second opinion ---
#
# Vaktene under driver RUNNEREN, ikke politikk-klassene. AST-vakten over beviser
# at gaten konstrueres; den beviser ikke at verdiktet brukes til noe. Det er
# noeyaktig hullet BL-4029 L4 falt i, saa begge maa finnes.


def _so(status, **over):
    from agent.second_opinion import SecondOpinionOutcome, SecondOpinionStatus

    base = dict(status=getattr(SecondOpinionStatus, status), reason="because",
                provenance="anthropic.api", model="claude-opus-5", confidence=0.9)
    base.update(over)
    return SecondOpinionOutcome(**base)


def _unreachable_landing(_evidence):
    """F3: en landing som IKKE skal skje.

    Reviewer flyttet `landing(evidence)` til FOER steg 10b og fikk hele suiten
    groenn -- altsaa en commit som skjer, og deretter et maal som merkes BLOCKED.
    I produksjon er `landing` `landing_callable._land`, som gjoer den ekte
    commiten. Rekkefoelgen mellom de to linjene var uvoktet.

    Idiomet finnes allerede i repoet (`tests/test_flyby_promote.py`); det manglet
    bare her.
    """
    pytest.fail("landing must be unreachable when the second opinion blocks")


def _run_10b(*, opinion, confidence=0.95, files=1, lines=5,
             landing_set=("a.py",), lease="a.py", diff="--- a\n+++ b\n+x",
             landing=None):
    ev = PreflightInput(
        git_clean=True, lease_clear=True, cad_status="fresh", adr_status="accepted",
        bl_status="open", obsidian_status="fresh",
        source_refs={"git": "g", "lease": lease, "cad": "C", "adr": "A", "bl": "B"})
    land = LandingEvidence(
        "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
        "log", "state", "closer", landing_set=landing_set)
    return GovernedCodeRunner(
        second_opinion=(lambda change, **kw: opinion) if opinion else None
    ).run(
        FaberGoal("g-so", "run", cad_ref="C", adr_ref="A", bl_ref="B"),
        preflight=PreflightResult(PreflightStatus.PASS, (), ev),
        build=lambda: {"tests": "ok", "diff_id": "d1", "changed_files": files,
                       "changed_lines": lines, "diff": diff},
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "d1", "sol",
                                        confidence=confidence),
        landing=landing or (lambda e: land),
        prelanding_evidence=land,
    )


def test_second_opinion_DISSENT_blocks_a_reviewer_PASS():
    """Uenighet blokkerer nedover.

    Kostnaden er asymmetrisk: aa blokkere foer landing er billig og reversibelt,
    aa lande en gal endring er ingen av delene. Alternativet -- loggfoer begge
    stemmer og land likevel -- gjoer andre-meningen til dekorasjon, som er
    defekten den skulle fjerne.
    """
    r = _run_10b(opinion=_so("DISSENT"), confidence=0.5,
                 landing=_unreachable_landing)
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "second_opinion_dissent"
    # F2: loggfoeringen er UBETINGET, saa den maa voktes paa BEGGE stier. Uten
    # denne linjen overlevde mutanten som droppet `extra=votes`.
    assert "second_opinion_votes" in r.goal.evidence


def test_second_opinion_ESCALATE_routes_to_the_owner():
    r = _run_10b(opinion=_so("ESCALATE"), confidence=0.5,
                 landing=_unreachable_landing)
    assert r.goal.state is GoalState.BLOCKED
    assert "owner_approval" in r.goal.evidence["next_step"]
    assert "second_opinion_votes" in r.goal.evidence


def test_no_answer_is_not_a_passed_second_opinion():
    """Fravaer av data er ikke et positivt funn -- og gaten har SIN EGEN grunn.

    UNAVAILABLE og DISSENT blokkerer begge, men krever helt ulike inngrep. En
    felles «second opinion failed» ville gjort dem umulige aa skille i journalen.
    """
    from agent.second_opinion import SecondOpinionOutcome

    r = _run_10b(opinion=SecondOpinionOutcome.unavailable("upstream timed out"),
                 confidence=0.5, landing=_unreachable_landing)
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "second_opinion_unavailable"
    assert r.handoff.required_gate != "second_opinion_dissent"
    assert "second_opinion_votes" in r.goal.evidence


def test_a_runner_with_no_injected_reviewer_uses_the_real_one_and_fails_closed(
        tmp_path, monkeypatch):
    """`None` betyr «bruk den ekte klienten», ALDRI «hopp over steget».

    Et skip-on-None ville gjort andre-meningen valgfri for den som konstruerer
    runneren -- altsaa avskrudd av produsenten, som er nettopp defekten gaten
    finnes for.

    F4: noekkelstien pekes eksplisitt paa en fil som ikke finnes. Foer var testen
    groenn fordi standardstien tilfeldigvis var tom paa .15 -- altsaa groenn FORDI
    kontrollen var avskrudd. Med en ekte noekkel paa plass ville den samme testen
    gjort et FAKTURERT Opus-kall og deretter feilet paa svaret. Det er gatens egen
    defektklasse: fravaer i suksessens forkledning.
    """
    monkeypatch.setenv("SECOND_OPINION_API_KEY_FILE", str(tmp_path / "absent"))
    r = _run_10b(opinion=None, confidence=None, landing=_unreachable_landing)
    assert r.goal.state is GoalState.BLOCKED
    # Den PRESISE aarsaken naar helt fram: noekkelfila mangler. Et generisk
    # "unavailable" ville sagt «noe gikk galt» til en loop som skal handle.
    assert r.handoff.required_gate == "second_opinion_credential"
    # ... og next_step navngir ÉN handling, ikke to alternativer der ett gjelder.
    assert "0600" in r.goal.evidence["next_step"]


def test_a_confident_reviewer_does_not_close_the_gate_on_blast_radius():
    """DETTE er testen som gjoer andre-meningen ekte.

        En second opinion som bare paakalles naar man allerede er i tvil,
        kalles aldri naar man tar feil med selvtillit.

    Confidence 1.0 og en stor endring: utloeseren maa fyre likevel. Hvis denne
    faller fordi noen gjorde utloeseren rent confidence-basert, er gaten
    redusert til et tvil-flagg.
    """
    r = _run_10b(opinion=_so("DISSENT"), confidence=1.0, files=6, lines=300)
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "second_opinion_dissent"


def test_a_confident_reviewer_does_not_close_the_gate_on_the_governance_surface():
    """Samme poeng, andre akse: en endring i selve vaktmaskineriet."""
    r = _run_10b(opinion=_so("DISSENT"), confidence=1.0,
                 landing_set=("agent/code_workflow.py",),
                 lease="agent/code_workflow.py")
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "second_opinion_dissent"


def test_a_small_confident_change_is_not_charged_for_an_opus_call():
    """Utloeseren er smal MED VILJE.

    Det er derfor fail-closed er til aa leve med: hadde gaten fyrt paa alt,
    ville et API-utfall stanset all landing, noen ville lagt inn en bypass --
    og bypassen ville vaert defekten.
    """
    def _must_not_be_called(change, **kw):
        raise AssertionError("second opinion consulted for a small, confident change")

    r2 = GovernedCodeRunner(second_opinion=_must_not_be_called)
    ev = PreflightInput(
        git_clean=True, lease_clear=True, cad_status="fresh", adr_status="accepted",
        bl_status="open", obsidian_status="fresh",
        source_refs={"git": "g", "lease": "a.py", "cad": "C", "adr": "A", "bl": "B"})
    land = LandingEvidence("sha", ReviewVerdict.PASS, "tests", "readback", "smoke",
                           "rollback", "log", "state", "closer", landing_set=("a.py",))
    result = r2.run(
        FaberGoal("g-cheap", "run", cad_ref="C", adr_ref="A", bl_ref="B"),
        preflight=PreflightResult(PreflightStatus.PASS, (), ev),
        build=lambda: {"tests": "ok", "diff_id": "d1", "changed_files": 1,
                       "changed_lines": 5, "diff": "x"},
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "d1", "sol", confidence=0.99),
        landing=lambda e: land,
        prelanding_evidence=land,
    )
    assert result.goal.state is GoalState.LANDED
    assert "second_opinion_votes" not in result.goal.evidence


def test_both_votes_are_recorded_on_the_path_that_actually_LANDS():
    """Loggfoering er ubetinget, ikke uenighetspolitikken.

    Denne fanget en EKTE defekt under verifiseringen: foerste utkast la stemmene
    bare i `evidence`-dicten, som gaar til landing()-adapteren og aldri til
    maalets egen evidens. Uenighet ble loggfoert paa BLOCK, mens enighet
    forsvant paa den stien som faktisk landet -- altsaa borte nettopp der man
    senere vil sporre «kjoerte gaten i det hele tatt?».
    """
    r = _run_10b(opinion=_so("CONCUR"), confidence=0.5)
    assert r.goal.state is GoalState.LANDED
    votes = r.goal.evidence["second_opinion_votes"]
    assert "reviewer=" in votes and "second_opinion=" in votes
    assert "anthropic.api" in votes


def test_a_smuggled_non_independent_CONCUR_cannot_land():
    """Mortens direktiv, paa den haandhevede stien.

    En modell som spoer seg selv er ikke en andre mening. Reviewer reproduserte
    dette som en bestaatt CONCUR foer uavhengighetssjekken ble flyttet inn i
    `resolve_disagreement` selv.
    """
    r = _run_10b(opinion=_so("CONCUR", provenance="cortex.13:1234",
                             model="qwen3-235b"), confidence=0.5)
    assert r.goal.state is GoalState.BLOCKED
    assert r.handoff.required_gate == "second_opinion_independence"


def test_production_shaped_build_evidence_reaches_CONCUR():
    """F1, ende-til-ende: naar steg 8 leverer det den faktisk leverer, LANDER det.

    Alle de andre 10b-vaktene mater runneren en haandskrevet diff. Denne bruker
    noekkelsettet `FaberImplementer.build` faktisk returnerer, og fanger dermed
    tilfellet reviewer maalte: gaten var teknisk korrekt og likevel en VEGG, fordi
    ingen produsent satte feltet den leser.
    """
    from agent.faber_implementer import render_review_diff

    diff = render_review_diff({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    assert diff.strip(), "precondition: the renderer must produce something"

    ev = PreflightInput(
        git_clean=True, lease_clear=True, cad_status="fresh", adr_status="accepted",
        bl_status="open", obsidian_status="fresh",
        source_refs={"git": "g", "lease": "a.py", "cad": "C", "adr": "A", "bl": "B"})
    land = LandingEvidence(
        "sha", ReviewVerdict.PASS, "tests", "readback", "smoke", "rollback",
        "log", "state", "closer", landing_set=("a.py",))
    result = GovernedCodeRunner(second_opinion=lambda change, **kw: _so("CONCUR")).run(
        FaberGoal("g-prod", "run", cad_ref="C", adr_ref="A", bl_ref="B"),
        preflight=PreflightResult(PreflightStatus.PASS, (), ev),
        # Noekkelsettet fra FaberImplementer.build, verbatim.
        build=lambda: {
            "changed_files": 1, "changed_lines": 2, "added_lines": 1,
            "deleted_lines": 1, "new_dependencies": 0,
            "diff_id": "faber8-deadbeefdeadbeef", "model": "stub",
            "design_ref": "/tmp/design.json",
            "blast_radius_source": "measured:pre-image-diff",
            "written_files": "a.py", "rationale": "bump", "tests": "ok",
            "diff": diff,
        },
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "faber8-deadbeefdeadbeef",
                                        "sol", confidence=0.5),
        landing=lambda e: land,
        prelanding_evidence=land,
    )
    assert result.goal.state is GoalState.LANDED
    assert "second_opinion_votes" in result.goal.evidence
