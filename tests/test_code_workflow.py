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
    for gate in ("BlGate", "DesignGate"):
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
    result = GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        preflight=preflight,
        build=lambda: {"tests": "pass", "diff_id": "diff-g1", "changed_files": 2, "changed_lines": 40},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "diff-g1", "sol"),
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
    base = dict(tests="pass", diff_id="diff-current", changed_files=1, changed_lines=8)
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
    new_calls = calls[len(calls_after_first):]
    assert set(new_calls) == {"tests", "runtime_smoke"}, new_calls
    assert "commit_closer" not in new_calls
    assert set(second.replayed) == {"commit_closer", "brain_change_log", "selfstate",
                                    "readback", "rollback"}
    assert set(second.executed) == {"tests", "runtime_smoke"}


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
