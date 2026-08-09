import json
from pathlib import Path

import pytest

from agent.code_workflow import (
    FaberGoal,
    FaberGoalRegistry,
    GovernedCodeRunner,
    GoalState,
    LandingEvidence,
    PreflightGate,
    PreflightInput,
    PreflightStatus,
    ReviewEvidence,
    ReviewVerdict,
)
from agent.flyby_promote import (
    PromotionBlocked,
    build_goal,
    load_manifest,
    promote,
)

MANIFEST = Path(__file__).resolve().parents[1] / "agent" / "flyby_promotions" / "bl3632_seven_workstreams.json"


def packet(**overrides):
    base = {
        "candidate_key": "candidate_example_2026_08_03",
        "slug": "example",
        "title": "Example candidate",
        "bl_ref": "BL-9999",
        "gate": "reviewer",
        "gate_class": "reviewer/landing gate",
        "epistemic_status": "observert",
        "repo_scope": "hermes-agent: agent/example.py",
        "rollback": "git revert",
        "next_step": "claim the lease",
        "acceptance": ["one criterion"],
    }
    base.update(overrides)
    return base


def passing_preflight():
    return PreflightGate().evaluate(
        PreflightInput(
            git_clean=True,
            lease_clear=True,
            cad_status="verified",
            adr_status="accepted",
            bl_status="open",
            obsidian_status="fresh",
            source_refs={k: k for k in ("git", "commit", "lease", "cad", "adr", "bl", "graph", "obsidian")},
        )
    )


# --- promotion packet contract -------------------------------------------------

def test_promoted_goal_enters_at_candidate_and_carries_full_provenance():
    goal = build_goal(packet(), promoted_by="claude:BL-3632", promoted_at="2026-08-04T00:00:00Z")
    # The runner owns candidate -> proposed; entering as proposed dead-ends it.
    assert goal.state is GoalState.CANDIDATE
    assert goal.owner == "faber" and goal.projection == "code"
    assert goal.goal_id == "faber.code.flyby:example"
    assert goal.bl_ref == "BL-9999"
    assert goal.evidence["trace_id"] == "flyby:example"
    assert goal.evidence["candidate_key"] == "candidate_example_2026_08_03"
    assert goal.evidence["promoted_by"] == "claude:BL-3632"


@pytest.mark.parametrize("field", ["candidate_key", "bl_ref", "gate", "repo_scope", "rollback", "next_step"])
def test_partial_packet_is_blocked_not_best_effort(field):
    with pytest.raises(PromotionBlocked):
        build_goal(packet(**{field: ""}), promoted_by="x", promoted_at="t")


def test_acceptance_criteria_are_mandatory():
    with pytest.raises(PromotionBlocked):
        build_goal(packet(acceptance=[]), promoted_by="x", promoted_at="t")


def test_bl_ref_must_be_a_bl_reference():
    with pytest.raises(PromotionBlocked):
        build_goal(packet(bl_ref="3633"), promoted_by="x", promoted_at="t")


def test_promotion_never_fabricates_gate_evidence():
    goal = build_goal(packet(), promoted_by="x", promoted_at="t")
    assert goal.cad_ref == "" and goal.adr_ref == ""
    assert goal.evidence["cad_status"] == "unknown"
    assert goal.evidence["adr_status"] == "unknown"
    assert goal.evidence["lease"] == "not_claimed"
    assert goal.evidence["preflight"] == "not_run"
    # The BL number is allocated but its ledger node only exists after commit.
    assert goal.evidence["bl_status"] == "reserved"


# --- the promoted goal must not arrive pre-cleared -----------------------------

def test_the_promoters_own_unknowns_are_what_block_preflight():
    """Everything else is supplied as PASS-worthy, so only the promoter's
    unknown CAD/ADR can be responsible for the BLOCK."""
    goal = build_goal(packet(), promoted_by="x", promoted_at="t")
    result = PreflightGate().evaluate(
        PreflightInput(
            git_clean=True,
            lease_clear=True,
            cad_status=goal.evidence["cad_status"],
            adr_status=goal.evidence["adr_status"],
            bl_status="open",
            obsidian_status="fresh",
            source_refs={k: k for k in ("git", "commit", "lease", "cad", "adr", "bl", "graph", "obsidian")},
        )
    )
    assert result.status is PreflightStatus.BLOCK
    assert any("CAD" in reason for reason in result.reasons)
    assert any("ADR" in reason for reason in result.reasons)


def test_owner_gated_goal_cannot_advance_even_on_a_passing_preflight():
    """The morten gate must be enforced by the runner, not just recorded."""
    goal = build_goal(packet(gate="morten"), promoted_by="x", promoted_at="t")
    result = GovernedCodeRunner().run(
        goal,
        preflight=passing_preflight(),
        build=lambda: pytest.fail("build must be unreachable behind an owner gate"),
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        landing=lambda evidence: pytest.fail("landing must be unreachable"),
    )
    assert result.goal.state is GoalState.BLOCKED
    assert "owner gate 'morten'" in result.blocker
    assert result.handoff.required_gate == "owner_gate"


def test_recorded_owner_approval_releases_the_gate():
    goal = build_goal(
        packet(gate="morten", cad_ref="CAD-M", adr_ref="ADR-038"),
        promoted_by="x",
        promoted_at="t",
    )
    approved = FaberGoal(**{**goal.__dict__, "evidence": {**goal.evidence, "owner_approval": "morten:2026-08-04"}})
    result = GovernedCodeRunner().run(
        approved,
        preflight=passing_preflight(),
        build=lambda: {"tests": "pass", "diff_id": "d"},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
    )
    assert result.goal.state is GoalState.LANDED


def test_reviewer_gated_goal_is_not_caught_by_the_owner_gate():
    result = GovernedCodeRunner().run(
        build_goal(packet(cad_ref="CAD-M", adr_ref="ADR-038"), promoted_by="x", promoted_at="t"),
        preflight=passing_preflight(),
        build=lambda: {"tests": "pass", "diff_id": "d"},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
    )
    assert result.goal.state is GoalState.LANDED


def test_goals_without_a_gate_field_are_unaffected():
    result = GovernedCodeRunner().run(
        FaberGoal("legacy", "pre-existing goal", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-1"),
        preflight=passing_preflight(),
        build=lambda: {"tests": "pass", "diff_id": "d"},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
    )
    assert result.goal.state is GoalState.LANDED


# --- registry durability -------------------------------------------------------

def test_a_stale_registry_does_not_erase_goals_another_writer_added(tmp_path):
    """Every agent session builds a registry at startup and holds it for the
    session; a later put() must not rewrite the file from that old snapshot."""
    path = tmp_path / "goals.json"
    stale = FaberGoalRegistry(path)  # loaded while the file was empty
    promote([packet()], FaberGoalRegistry(path), promoted_by="claude:BL-3632")
    stale.put(FaberGoal("faber.code.other", "another writer's goal"))
    on_disk = FaberGoalRegistry(path)
    assert set(goal.goal_id for goal in on_disk.all()) == {
        "faber.code.flyby:example",
        "faber.code.other",
    }


def test_a_write_refuses_to_overwrite_an_unreadable_registry(tmp_path):
    path = tmp_path / "goals.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable goal registry"):
        FaberGoalRegistry(path).put(FaberGoal("faber.code.x", "x"))
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_batch_promotion_is_a_single_durable_write(tmp_path, monkeypatch):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    saves = {"n": 0}
    original = FaberGoalRegistry._save

    def counting_save(self):
        saves["n"] += 1
        return original(self)

    monkeypatch.setattr(FaberGoalRegistry, "_save", counting_save)
    promote([packet(slug="a"), packet(slug="b"), packet(slug="c")], registry, promoted_by="x")
    assert saves["n"] == 1
    assert len(FaberGoalRegistry(tmp_path / "goals.json").all()) == 3


# --- idempotency and clobber protection ---------------------------------------

def test_promotion_is_idempotent_and_queues_the_goal(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    first = promote([packet()], registry, promoted_by="claude:BL-3632")
    assert first[0]["action"] == "installed"
    assert registry.next_operational_goal().goal_id == "faber.code.flyby:example"
    second = promote([packet()], registry, promoted_by="claude:BL-3632")
    assert second[0]["action"] == "updated"
    assert len(registry.all()) == 1


def test_a_promoted_goal_is_dequeued_and_blocks_for_the_right_reason(tmp_path):
    """Guards the dead-end: a goal installed in the wrong state makes the runner
    raise on its own first transition, which would look like a governance BLOCK
    while really being a broken install.  The only thing that may stop a freshly
    promoted goal is its missing CAD/ADR evidence."""
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    queued = registry.next_operational_goal()
    assert queued.goal_id == "faber.code.flyby:example"
    result = GovernedCodeRunner().run(
        queued,
        preflight=passing_preflight(),
        build=lambda: pytest.fail("build must be unreachable without CAD/ADR"),
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        landing=lambda evidence: pytest.fail("landing must be unreachable"),
    )
    assert "invalid goal transition" not in result.blocker
    assert "cad_ref, adr_ref" in result.blocker
    assert result.goal.state is GoalState.BLOCKED


def test_a_blocked_goal_is_routinely_re_promotable(tmp_path):
    """BLOCKED is where a governed tick parks a goal awaiting evidence, so
    re-promoting must not require the destructive force flag."""
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(FaberGoal("faber.code.flyby:example", "Example", state=GoalState.BLOCKED))
    promote([packet()], registry, promoted_by="x")
    assert registry.get("faber.code.flyby:example").state is GoalState.CANDIDATE


def test_promotion_refuses_to_reset_a_goal_that_already_advanced(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(FaberGoal("faber.code.flyby:example", "Example", state=GoalState.BUILDING))
    with pytest.raises(PromotionBlocked):
        promote([packet()], registry, promoted_by="x")
    assert registry.get("faber.code.flyby:example").state is GoalState.BUILDING


def test_force_is_scoped_to_one_named_goal(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(FaberGoal("faber.code.flyby:a", "A", state=GoalState.BUILDING))
    registry.put(FaberGoal("faber.code.flyby:b", "B", state=GoalState.LANDED))
    with pytest.raises(PromotionBlocked):
        promote(
            [packet(slug="a"), packet(slug="b")],
            registry,
            promoted_by="x",
            force_goal_ids=["faber.code.flyby:a"],
        )
    assert registry.get("faber.code.flyby:b").state is GoalState.LANDED
    assert registry.get("faber.code.flyby:a").state is GoalState.BUILDING


def test_a_goal_advanced_by_another_writer_is_not_reset_by_a_stale_promoter(tmp_path):
    """The caller's snapshot cannot see a concurrent advance, so the guard has
    to be enforced inside the registry's write lock."""
    path = tmp_path / "goals.json"
    stale = FaberGoalRegistry(path)  # snapshot taken while the goal did not exist
    FaberGoalRegistry(path).put(
        FaberGoal("faber.code.flyby:example", "Example", state=GoalState.LANDED)
    )
    with pytest.raises(ValueError, match="already advanced"):
        promote([packet()], stale, promoted_by="x")
    assert FaberGoalRegistry(path).get("faber.code.flyby:example").state is GoalState.LANDED


def test_an_autonomt_gate_is_not_mistaken_for_an_owner_gate():
    """autonomt|reviewer|morten is the Flyby intake vocabulary; autonomt means
    no owner decision is needed, so it must not dead-end the runner."""
    result = GovernedCodeRunner().run(
        build_goal(packet(gate="autonomt", cad_ref="CAD-M", adr_ref="ADR-038"), promoted_by="x", promoted_at="t"),
        preflight=passing_preflight(),
        build=lambda: {"tests": "pass", "diff_id": "d"},
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        prelanding_evidence=LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
        landing=lambda evidence: LandingEvidence("sha", ReviewVerdict.PASS, "t", "r", "s", "rb", "l", "st", "c"),
    )
    assert result.goal.state is GoalState.LANDED


def test_an_unrecognised_gate_value_still_fails_closed():
    result = GovernedCodeRunner().run(
        build_goal(packet(gate="whatever", cad_ref="CAD-M", adr_ref="ADR-038"), promoted_by="x", promoted_at="t"),
        preflight=passing_preflight(),
        build=lambda: pytest.fail("build must be unreachable behind an unknown gate"),
        review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        landing=lambda evidence: pytest.fail("landing must be unreachable"),
    )
    assert result.goal.state is GoalState.BLOCKED
    assert result.handoff.required_gate == "owner_gate"


def test_force_must_name_a_goal_in_the_batch(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    with pytest.raises(PromotionBlocked, match="not in this batch"):
        promote([packet()], registry, promoted_by="x", force_goal_ids=["faber.code.flyby:typo"])


def test_batch_is_all_or_nothing_when_one_packet_would_clobber(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(FaberGoal("faber.code.flyby:b", "B", state=GoalState.LANDED))
    with pytest.raises(PromotionBlocked):
        promote([packet(slug="a"), packet(slug="b")], registry, promoted_by="x")
    assert FaberGoalRegistry(tmp_path / "goals.json").get("faber.code.flyby:a") is None


def test_duplicate_slugs_in_one_batch_are_blocked(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    with pytest.raises(PromotionBlocked):
        promote([packet(), packet()], registry, promoted_by="x")


# --- the actual seven ----------------------------------------------------------

def test_manifest_promotes_the_seven_workstreams(tmp_path):
    packets, promoted_by = load_manifest(MANIFEST)
    assert len(packets) == 7
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    results = promote(packets, registry, promoted_by=promoted_by)
    assert {r["bl_ref"] for r in results} == {f"BL-{n}" for n in range(3633, 3640)}
    assert len(registry.all()) == 7
    assert all(goal.state is GoalState.CANDIDATE for goal in registry.all())
    gates = {r["goal_id"].split(":")[1]: r["gate"] for r in results}
    assert gates["symbiose_security_assessment_baseline"] == "morten"
    assert gates["cyber_control_plane_detection_audit"] == "morten"
    assert gates["lukket_sporbar_autonom_laringsloyfe"] == "morten"
    assert gates["governed_code_runner_sol_followups"] == "reviewer"


def test_every_morten_gated_workstream_is_held_by_the_owner_gate(tmp_path):
    packets, promoted_by = load_manifest(MANIFEST)
    held = []
    for pkt in packets:
        if pkt["gate"] != "morten":
            continue
        goal = build_goal(pkt, promoted_by=promoted_by, promoted_at="t")
        result = GovernedCodeRunner().run(
            goal,
            preflight=passing_preflight(),
            build=lambda: pytest.fail(f"{goal.goal_id} reached build behind a morten gate"),
            review=lambda evidence: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
            landing=lambda evidence: pytest.fail("landing reached"),
        )
        assert result.goal.state is GoalState.BLOCKED
        held.append(goal.bl_ref)
    assert sorted(held) == ["BL-3635", "BL-3636", "BL-3637"]


def test_manifest_must_name_its_promoter(tmp_path):
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload.pop("promoted_by")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PromotionBlocked):
        load_manifest(bad)
