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
from agent.faber_runtime import FaberRuntime, handoff_path


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
            "lease": "lease:faber",
            "cad": "CAD-M",
            "adr": "ADR-038",
            "bl": "BL-3254",
            "obsidian": "Brain/Change Log.md",
            "commit": "commit:local",
            "graph": "graph:read-after-write",
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
    )
    assert result.run.goal.state is GoalState.LANDED
