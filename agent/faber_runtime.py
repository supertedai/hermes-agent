"""Runtime binding for the governed Faber Code workflow.

This adapter is intentionally small: evidence collection stays outside the
workflow kernel, while this boundary makes PreflightResult mandatory before a
Faber build can run and persists a blocked handoff for the next tick.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from agent.code_workflow import (
    FaberGoal,
    FaberHandoff,
    FaberGoalRegistry,
    GovernedCodeRunner,
    HandoffStore,
    LandingEvidence,
    PreflightGate,
    PreflightInput,
    PreflightResult,
    ReviewEvidence,
    ReviewVerdict,
    GovernedRunResult,
)


@dataclass(frozen=True)
class FaberRuntimeResult:
    """Result of one runtime tick at the governed Code boundary."""

    run: GovernedRunResult
    preflight: PreflightResult


class FaberRuntime:
    """Bind source evidence, the hard preflight gate, and the runner.

    The adapter never invents evidence and never commits or starts services.
    A failed preflight is converted into a blocked goal and, when configured,
    an atomic handoff file for the next tick.
    """

    def __init__(
        self,
        *,
        preflight: PreflightGate | None = None,
        runner: GovernedCodeRunner | None = None,
        handoff_store: HandoffStore | None = None,
        goal_registry: FaberGoalRegistry | None = None,
    ) -> None:
        self.preflight_gate = preflight or PreflightGate()
        self.runner = runner or GovernedCodeRunner()
        self.handoff_store = handoff_store
        self.goal_registry = goal_registry

    def tick(
        self,
        goal: FaberGoal,
        evidence: PreflightInput,
        *,
        build: Callable[[], Mapping[str, str]],
        review: Callable[[Mapping[str, str]], ReviewEvidence],
        landing: Callable[[Mapping[str, str]], LandingEvidence],
        prelanding_evidence: LandingEvidence | None = None,
    ) -> FaberRuntimeResult:
        """Run exactly one governed tick; build is unreachable without PASS."""
        if self.goal_registry is not None:
            self.goal_registry.put(goal)
        preflight = self.preflight_gate.evaluate(evidence)
        result = self.runner.run(
            goal,
            preflight=preflight,
            build=build,
            review=review,
            landing=landing,
            prelanding_evidence=prelanding_evidence,
        )
        if result.handoff is not None and self.handoff_store is not None:
            self.handoff_store.save(result.handoff)
        if self.goal_registry is not None:
            self.goal_registry.put(result.goal)
        return FaberRuntimeResult(run=result, preflight=preflight)


def handoff_path(path: str | Path) -> HandoffStore:
    """Create the profile/repo-local durable handoff adapter."""
    return HandoffStore(path)


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one Faber preflight evidence record.")
    parser.add_argument("--evidence-json", required=True, help="JSON object containing PreflightInput fields")
    args = parser.parse_args()
    try:
        payload = json.loads(args.evidence_json)
        evidence = PreflightInput(**payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCK", "reasons": [f"invalid evidence: {exc}"]}))
        return 2
    result = FaberRuntime().preflight_gate.evaluate(evidence)
    print(json.dumps({"status": result.status.value, "reasons": result.reasons, "evidence": asdict(result.evidence)}))
    return 0 if result.status.value == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(_cli())
