"""Runtime binding for the governed Faber Code workflow.

This adapter is intentionally small: evidence collection stays outside the
workflow kernel, while this boundary makes PreflightResult mandatory before a
Faber build can run and persists a blocked handoff for the next tick.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from agent.code_workflow import (
    FaberGoal,
    FaberHandoff,
    FaberGoalRegistry,
    GoalState,
    GovernedCodeRunner,
    HandoffStore,
    LandingEvidence,
    PreflightGate,
    PreflightInput,
    PreflightResult,
    PostcommitResult,
    ReviewEvidence,
    ReviewVerdict,
    GovernedRunResult,
)


@dataclass(frozen=True)
class FaberRuntimeResult:
    """Result of one runtime tick at the governed Code boundary."""

    run: GovernedRunResult
    preflight: PreflightResult
    postcommit: PostcommitResult | None = None
    learning_event: Mapping[str, object] | None = None


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
        postcommit: Callable[[GovernedRunResult], PostcommitResult] | None = None,
        learning: Callable[[GovernedRunResult, PostcommitResult], Mapping[str, object]] | None = None,
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
        postcommit_result = (
            postcommit(result)
            if postcommit is not None and result.goal.state is GoalState.LANDED
            else None
        )
        learning_event = (
            dict(learning(result, postcommit_result))
            if learning is not None and postcommit_result is not None and postcommit_result.success
            else None
        )
        if result.handoff is not None and self.handoff_store is not None:
            self.handoff_store.save(result.handoff)
        if self.goal_registry is not None:
            self.goal_registry.put(result.goal)
        return FaberRuntimeResult(run=result, preflight=preflight, postcommit=postcommit_result, learning_event=learning_event)


def handoff_path(path: str | Path) -> HandoffStore:
    """Create the profile/repo-local durable handoff adapter."""
    return HandoffStore(path)


def build_callable(payload: Mapping[str, object], runner: GovernedCodeRunner,
                   evidence: PreflightInput) -> Callable[[], Mapping[str, object]]:
    """Velg hva steg 8 faktisk ER for denne ticken.

    BL-4050. Til nå fantes bare den ene grenen::

        build=lambda: payload["build"]

    Kjeden leste altså sin egen blast-radius ut av det samme JSON-objektet som ba
    den om å kjøre. Vakten fra BL-4029 var ekte, men den dømte et tall avsenderen
    hadde skrevet selv — en måling som er et sitat.

    Med ``payload["implement"]`` bygges i stedet en :class:`FaberImplementer`, som
    kaller cortex, skriver filer og MÅLER endringen fra bytes på disk.

    To ting bindes her, og begge er poenget:

    * **Budsjettet** hentes fra runneren (``bound_to``), ikke fra payloaden. Ellers
      finnes to grenser som kan være uenige.
    * **Lease-settet** hentes fra ``source_refs["lease"]`` — nøyaktig den referansen
      steg 4 sjekket og steg 11 sammenligner landingssettet mot. Å la payloaden
      oppgi et eget lease-sett ville gitt skriveren lov til å definere sin egen
      grense, og da beviser hverken steg 4 eller steg 11 noe.

    Den literale grenen beholdes for replay og testrigger, men den er nå navngitt
    som det den er, ikke som en utfører.
    """
    spec = payload.get("implement")
    if not spec:
        literal = payload.get("build")
        if literal is None:
            raise ValueError("tick payload needs either 'implement' or a literal 'build'")
        return lambda: dict(literal)  # type: ignore[arg-type]
    if not isinstance(spec, Mapping):
        raise ValueError("'implement' must be an object")
    from agent.faber_implementer import DesignStore, FaberImplementer

    lease = tuple(
        part.strip()
        for part in str(evidence.source_refs.get("lease", "")).split(",")
        if part.strip()
    )
    if not lease:
        raise ValueError(
            "source_refs['lease'] names no files — the writer cannot be confined to "
            "a lease that does not say what it covers")
    goal_spec = payload.get("goal") or {}
    implementer = FaberImplementer.bound_to(
        runner,
        goal_id=str(spec.get("goal_id") or (goal_spec.get("goal_id") if isinstance(goal_spec, Mapping) else "")),
        repo_root=str(spec["repo_root"]),
        lease_set=lease,
        design_store=DesignStore(spec["design_root"]) if spec.get("design_root") else None,
        test_command=tuple(spec["test_command"]) if spec.get("test_command") else None,
    )
    return implementer.build


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run one governed Faber runtime tick.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--evidence-json", help="JSON object containing PreflightInput fields")
    group.add_argument("--tick-json", help="JSON object containing goal, evidence and deterministic tick evidence")
    group.add_argument("--memory-measure-query", help="Run one real MemoryManager enforcement measurement")
    group.add_argument("--propose-job-json", help="Create one consent-first Faber cron suggestion")
    args = parser.parse_args()
    try:
        if args.propose_job_json:
            from agent.faber_tui_egress import propose_faber_job
            record = propose_faber_job(**json.loads(args.propose_job_json))
            print(json.dumps({"status": "pending" if record else "deduplicated_or_capped", "record": record}, default=str))
            return 0 if record else 2
        if args.memory_measure_query:
            from agent.continuous_pipeline import CANONICAL_MEMORY_LAYER_IDS, MemoryLayerSpec, MemoryManagerBridge, MemoryScheduler
            from agent.memory_manager import MemoryManager
            bridge = MemoryManagerBridge(
                MemoryManager(),
                MemoryScheduler(tuple(MemoryLayerSpec(layer_id, "symbiose.canonical") for layer_id in CANONICAL_MEMORY_LAYER_IDS), require_canonical=True),
                strict=True,
                metrics_path=os.path.expanduser("~/.hermes-gui/faber/memory-enforcement.json"),
                source_scope="faber.codex",
            )
            hook = bridge.before_turn(args.memory_measure_query, phase="sense")
            print(json.dumps({"status": "OK", "selection": asdict(hook.selection), "source_scope": hook.source_scope, "metrics_path": str(bridge.metrics_path)}))
            return 0
        if args.evidence_json:
            evidence = PreflightInput(**json.loads(args.evidence_json))
            result = FaberRuntime().preflight_gate.evaluate(evidence)
            print(json.dumps({"status": result.status.value, "reasons": result.reasons, "evidence": asdict(result.evidence)}))
            return 0 if result.status.value == "PASS" else 2
        payload = json.loads(args.tick_json)
        goal = FaberGoal(**payload["goal"])
        evidence = PreflightInput(**payload["evidence"])
        review = ReviewEvidence(**payload["review"])
        landing = LandingEvidence(**payload["landing"])
        prelanding = LandingEvidence(**payload["prelanding"]) if payload.get("prelanding") else None
        runtime = FaberRuntime()
        result = runtime.tick(
            goal,
            evidence,
            build=build_callable(payload, runtime.runner, evidence),
            review=lambda _: review,
            landing=lambda _: landing,
            prelanding_evidence=prelanding,
        )
        print(json.dumps({"status": result.run.goal.state.value, "preflight": result.preflight.status.value, "reasons": result.run.handoff.blocker if result.run.handoff else []}, default=str))
        return 0 if result.run.goal.state.value in {"verified", "landed", "measured", "learned"} else 2
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCK", "reasons": [f"invalid tick payload: {exc}"]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
