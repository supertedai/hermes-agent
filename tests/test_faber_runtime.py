from __future__ import annotations

from pathlib import Path

from agent.code_workflow import (
    FaberGoal,
    LandingEvidence,
    PreflightInput,
    ReviewVerdict,
    ReviewEvidence,
    GoalState,
)
from agent.faber_runtime import FaberRuntime, PostcommitResult, handoff_path


def evidence(*, clean: bool = True):
    return PreflightInput(
        git_clean=clean,
        lease_clear=True,
        cad_status="verified",
        adr_status="accepted",
        bl_status="open",
        obsidian_status="fresh",
        source_refs={
            "git": "HEAD:agent/faber_runtime.py",
            # BL-4029 / ADR-062 V4 sjekk 2: lease-refen NAVNGIR filene, saa
            # landingssettet kan sammenlignes mot dem ved commit.
            "lease": "a.py,b.py",
            "cad": "CAD-M",
            "adr": "ADR-038",
            "bl": "BL-3254",
            "obsidian": "Brain/Change Log.md",
        },
    )


def landing(_evidence=None):
    return LandingEvidence(
        "sha",
        ReviewVerdict.PASS,
        "tests",
        "readback",
        "smoke",
        "rollback",
        "log",
        "state",
        "closer",
        # En landing maa oppgi HVILKE filer den roerer. Uten det er filsettet
        # ukjent, og en ukjent mengde kan ikke vaere en delmengde av leasen.
        landing_set=("a.py",),
    )


def test_runtime_blocks_before_build_and_persists_handoff(tmp_path: Path):
    called = False

    def build():
        nonlocal called
        called = True
        return {"tests": "must not run"}

    runtime = FaberRuntime(handoff_store=handoff_path(tmp_path / "handoff.json"))
    result = runtime.tick(
        FaberGoal("g1", "preflight test", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        evidence(clean=False),
        build=build,
        review=lambda _: ReviewVerdict.PASS,
        landing=landing,
    )

    assert result.preflight.status.value == "BLOCK"
    assert result.run.goal.state is GoalState.BLOCKED
    assert result.run.handoff is not None
    assert not called
    assert runtime.handoff_store is not None
    assert runtime.handoff_store.load() == result.run.handoff


def test_runtime_reaches_runner_only_after_preflight_pass():
    called = False

    def build():
        nonlocal called
        called = True
        return {"tests": "pass"}

    result = FaberRuntime().tick(
        FaberGoal("g2", "passing test", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        evidence(),
        build=build,
        review=lambda _: ReviewVerdict.BLOCK,
        landing=landing,
    )

    assert result.preflight.status.value == "PASS"
    assert called
    assert result.run.goal.state is GoalState.BLOCKED
    assert result.run.handoff is not None
    assert result.run.handoff.required_gate == "reviewer"


def test_faber_runtime_reaches_landed_with_prevalidated_dod():
    evidence_record = evidence()
    landing_record = landing()
    result = FaberRuntime().tick(
        FaberGoal("g3", "runtime landing", cad_ref="CAD-M", adr_ref="ADR-038", bl_ref="BL-3254"),
        evidence_record,
        build=lambda: {"tests": "pass", "diff_id": "diff-g3"},
        review=lambda _: ReviewEvidence(ReviewVerdict.PASS, "diff-g3", "sol"),
        prelanding_evidence=landing_record,
        landing=lambda _: landing_record,
        postcommit=lambda _: PostcommitResult(True, landing_record),
        learning=lambda _, __: {"metric": "quality", "validated": True, "skill_or_workflow": "faber"},
    )
    assert result.run.goal.state is GoalState.LANDED
    assert result.postcommit is not None
    assert result.postcommit.success is True
    assert result.learning_event == {"metric": "quality", "validated": True, "skill_or_workflow": "faber"}
