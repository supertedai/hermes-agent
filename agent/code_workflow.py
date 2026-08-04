"""Governed Code/Faber workflow gates.

This module is deliberately side-effect free. It turns the Code workflow rails
into typed, fail-closed decisions that can be fed by Hermes/Symbiose/CAD/ADR/BL
adapters without duplicating their storage.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping


class PreflightStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class GoalState(str, Enum):
    CANDIDATE = "candidate"
    PROPOSED = "proposed"
    APPROVED = "approved"
    PLANNED = "planned"
    BUILDING = "building"
    VERIFIED = "verified"
    LANDED = "landed"
    MEASURED = "measured"
    LEARNED = "learned"
    BLOCKED = "blocked"


class ReviewVerdict(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class ReviewEvidence:
    verdict: ReviewVerdict
    diff_id: str
    reviewer: str = ""


@dataclass(frozen=True)
class PreflightInput:
    """Evidence collected before code changes begin.

    Status values are intentionally strings so adapters can preserve source
    vocabulary (fresh/stale, accepted/proposed, open/blocked, etc.).
    """

    git_clean: bool
    lease_clear: bool
    cad_status: str
    adr_status: str
    bl_status: str
    obsidian_status: str
    source_refs: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PreflightResult:
    status: PreflightStatus
    reasons: tuple[str, ...]
    evidence: PreflightInput


class PreflightGate:
    """Fail-closed preflight evaluator for the Code/Faber workflow."""

    def evaluate(self, evidence: PreflightInput) -> PreflightResult:
        reasons: list[str] = []
        required_refs = ("git", "lease", "cad", "adr", "bl", "obsidian")
        missing_refs = tuple(ref for ref in required_refs if not evidence.source_refs.get(ref))
        if missing_refs:
            reasons.append("missing authoritative source refs: " + ", ".join(missing_refs))
        if not evidence.git_clean:
            reasons.append("git target is dirty or has unowned changes")
        if not evidence.lease_clear:
            reasons.append("target lease is not clear")
        if evidence.cad_status.lower() not in {"verified", "fresh", "accepted"}:
            reasons.append(f"CAD status is not fresh/verified: {evidence.cad_status}")
        if evidence.adr_status.lower() not in {"accepted", "verified", "fresh"}:
            reasons.append(f"ADR status is not accepted/fresh: {evidence.adr_status}")
        if evidence.bl_status.lower() not in {"open", "approved", "in_progress", "reviewed"}:
            reasons.append(f"BL status is not actionable: {evidence.bl_status}")
        if evidence.obsidian_status.lower() not in {"fresh", "verified", "accepted"}:
            reasons.append(f"Brain/Obsidian status is not fresh: {evidence.obsidian_status}")
        status = PreflightStatus.PASS if not reasons else PreflightStatus.BLOCK
        return PreflightResult(status, tuple(reasons), evidence)


@dataclass(frozen=True)
class FaberGoal:
    goal_id: str
    title: str
    owner: str = "faber"
    projection: str = "code"
    state: GoalState = GoalState.CANDIDATE
    cad_ref: str = ""
    adr_ref: str = ""
    bl_ref: str = ""
    rollback: str = ""
    evidence: Mapping[str, str] = field(default_factory=dict)
    blocked_from: GoalState | None = None
    blocker: str = ""
    next_step: str = ""


class FaberGoalRegistry:
    """Durable registry for Faber-owned operational goals."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path).expanduser() if path else None
        self._goals: dict[str, FaberGoal] = {}
        if self.path:
            self._load()

    def put(self, goal: FaberGoal) -> FaberGoal:
        if goal.owner != "faber" or goal.projection != "code":
            raise ValueError("goal registry accepts only Faber Code goals")
        self._goals[goal.goal_id] = goal
        self._save()
        return goal

    def get(self, goal_id: str) -> FaberGoal | None:
        return self._goals.get(goal_id)

    def all(self) -> tuple[FaberGoal, ...]:
        return tuple(self._goals.values())

    def next_operational_goal(self) -> FaberGoal | None:
        candidates = [
            goal for goal in self._goals.values()
            if goal.state in {GoalState.CANDIDATE, GoalState.PROPOSED, GoalState.BLOCKED}
        ]
        return sorted(candidates, key=lambda goal: goal.goal_id)[0] if candidates else None

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for goal in self._goals.values():
            item = asdict(goal)
            item["state"] = goal.state.value
            item["blocked_from"] = goal.blocked_from.value if goal.blocked_from else None
            payload.append(item)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for item in payload if isinstance(payload, list) else []:
                goal = FaberGoal(
                    goal_id=str(item["goal_id"]),
                    title=str(item["title"]),
                    owner=str(item.get("owner", "faber")),
                    projection=str(item.get("projection", "code")),
                    state=GoalState(str(item.get("state", GoalState.CANDIDATE.value))),
                    cad_ref=str(item.get("cad_ref", "")),
                    adr_ref=str(item.get("adr_ref", "")),
                    bl_ref=str(item.get("bl_ref", "")),
                    rollback=str(item.get("rollback", "")),
                    evidence=dict(item.get("evidence") or {}),
                    blocked_from=(GoalState(str(item["blocked_from"]))
                                 if item.get("blocked_from") else None),
                    blocker=str(item.get("blocker", "")),
                    next_step=str(item.get("next_step", "")),
                )
                if goal.owner == "faber" and goal.projection == "code":
                    self._goals[goal.goal_id] = goal
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._goals = {}


@dataclass(frozen=True)
class FaberHandoff:
    """Durable continuation packet for the next Faber job/tick."""

    goal_id: str
    owner: str
    projection: str
    blocked_from: GoalState
    blocker: str
    next_step: str
    required_gate: str
    evidence: Mapping[str, str] = field(default_factory=dict)


class HandoffStore:
    """Atomic profile-local handoff store for the next Faber job."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    def save(self, handoff: FaberHandoff) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(handoff)
        payload["blocked_from"] = handoff.blocked_from.value
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self) -> FaberHandoff | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return FaberHandoff(
                goal_id=str(payload["goal_id"]),
                owner=str(payload["owner"]),
                projection=str(payload["projection"]),
                blocked_from=GoalState(str(payload["blocked_from"])),
                blocker=str(payload["blocker"]),
                next_step=str(payload["next_step"]),
                required_gate=str(payload["required_gate"]),
                evidence=dict(payload.get("evidence") or {}),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None


_ALLOWED_TRANSITIONS: dict[GoalState, frozenset[GoalState]] = {
    GoalState.CANDIDATE: frozenset({GoalState.PROPOSED}),
    GoalState.PROPOSED: frozenset({GoalState.APPROVED, GoalState.CANDIDATE}),
    GoalState.APPROVED: frozenset({GoalState.PLANNED}),
    GoalState.PLANNED: frozenset({GoalState.BUILDING}),
    GoalState.BUILDING: frozenset({GoalState.VERIFIED, GoalState.PLANNED}),
    GoalState.VERIFIED: frozenset({GoalState.LANDED, GoalState.BUILDING}),
    GoalState.LANDED: frozenset({GoalState.MEASURED}),
    GoalState.MEASURED: frozenset({GoalState.LEARNED, GoalState.PROPOSED}),
    GoalState.LEARNED: frozenset({GoalState.PROPOSED}),
    GoalState.BLOCKED: frozenset({
        GoalState.PROPOSED,
        GoalState.APPROVED,
        GoalState.PLANNED,
        GoalState.BUILDING,
        GoalState.VERIFIED,
        GoalState.LANDED,
    }),
}


class GoalLedger:
    """Fail-closed state machine for Faber-owned operational goals."""

    def transition(
        self,
        goal: FaberGoal,
        target: GoalState,
        *,
        preflight: PreflightResult | None = None,
        review: ReviewVerdict = ReviewVerdict.PENDING,
        review_evidence: ReviewEvidence | None = None,
        evidence: Mapping[str, str] | None = None,
        landing_evidence: "LandingEvidence | None" = None,
    ) -> FaberGoal:
        if goal.owner != "faber" or goal.projection != "code":
            raise ValueError("goal is outside Faber's Code projection")
        if target is GoalState.BLOCKED:
            return replace(
                goal,
                state=GoalState.BLOCKED,
                blocked_from=goal.state,
                blocker=(evidence or {}).get("blocker", "gate required"),
                next_step=(evidence or {}).get("next_step", "resume after gate"),
                evidence={**goal.evidence, **(evidence or {})},
            )
        if goal.state is GoalState.BLOCKED:
            if goal.blocked_from is None or target is not goal.blocked_from:
                raise ValueError("blocked goal may only resume at its blocked state")
        elif target not in _ALLOWED_TRANSITIONS[goal.state]:
            raise ValueError(f"invalid goal transition: {goal.state.value} -> {target.value}")
        if target in {GoalState.APPROVED, GoalState.PLANNED, GoalState.BUILDING}:
            if preflight is None or preflight.status is not PreflightStatus.PASS:
                raise PermissionError("preflight PASS required before build planning")
            missing_refs = tuple(
                name for name, value in (("cad_ref", goal.cad_ref), ("adr_ref", goal.adr_ref), ("bl_ref", goal.bl_ref))
                if not value
            )
            if missing_refs:
                raise ValueError("goal references required before build: " + ", ".join(missing_refs))
        if target is GoalState.LANDED:
            if review_evidence is None or review_evidence.verdict is not ReviewVerdict.PASS:
                raise PermissionError("complete ReviewEvidence PASS required before landing")
            if not review_evidence.diff_id or not review_evidence.reviewer:
                raise PermissionError("review diff_id and reviewer required before landing")
        if target is GoalState.LANDED:
            if landing_evidence is None:
                raise ValueError("complete landing evidence required before landed")
            done, missing = DefinitionOfDone().evaluate(landing_evidence)
            if not done:
                raise ValueError("definition of done incomplete: " + ", ".join(missing))
        required_evidence = {
            GoalState.VERIFIED: "tests",
            GoalState.MEASURED: "runtime_smoke",
            GoalState.LEARNED: "effect_metric",
        }
        required = required_evidence.get(target)
        merged = dict(goal.evidence)
        merged.update(evidence or {})
        if required and not merged.get(required):
            raise ValueError(f"evidence required for {target.value}: {required}")
        return replace(goal, state=target, evidence=merged)

    def handoff(self, goal: FaberGoal, *, required_gate: str) -> FaberHandoff:
        if goal.state is not GoalState.BLOCKED or goal.blocked_from is None:
            raise ValueError("handoff requires a blocked goal")
        return FaberHandoff(
            goal_id=goal.goal_id,
            owner=goal.owner,
            projection=goal.projection,
            blocked_from=goal.blocked_from,
            blocker=goal.blocker,
            next_step=goal.next_step,
            required_gate=required_gate,
            evidence=goal.evidence,
        )


@dataclass(frozen=True)
class LandingEvidence:
    commit: str
    reviewer: ReviewVerdict
    tests: str
    readback: str
    runtime_smoke: str
    rollback: str
    brain_change_log: str
    selfstate: str
    commit_closer: str = ""


class DefinitionOfDone:
    """Post-work gate; all fields must be present and non-empty."""

    def evaluate(self, evidence: LandingEvidence) -> tuple[bool, tuple[str, ...]]:
        missing = tuple(
            name
            for name, value in (
                ("commit", evidence.commit),
                ("commit_closer", evidence.commit_closer),
                ("reviewer_pass", evidence.reviewer.value if evidence.reviewer is ReviewVerdict.PASS else ""),
                ("tests", evidence.tests),
                ("readback", evidence.readback),
                ("runtime_smoke", evidence.runtime_smoke),
                ("rollback", evidence.rollback),
                ("brain_change_log", evidence.brain_change_log),
                ("selfstate", evidence.selfstate),
            )
            if not value
        )
        return not missing, missing


@dataclass(frozen=True)
class GovernedRunResult:
    goal: FaberGoal
    handoff: FaberHandoff | None = None
    blocker: str = ""


class GovernedCodeRunner:
    """Single fail-closed runner for Faber's Code workflow.

    Callbacks are injected adapters for build/test/review/landing evidence.
    The runner owns ordering and state transitions; it never commits or starts
    infrastructure itself.
    """

    def __init__(self, ledger: GoalLedger | None = None):
        self.ledger = ledger or GoalLedger()

    def run(
        self,
        goal: FaberGoal,
        *,
        preflight: PreflightResult,
        build: Callable[[], Mapping[str, str]],
        review: Callable[[Mapping[str, str]], ReviewVerdict | ReviewEvidence],
        landing: Callable[[Mapping[str, str]], LandingEvidence],
        prelanding_evidence: LandingEvidence | None = None,
    ) -> GovernedRunResult:
        def blocked(current: FaberGoal, reason: str, gate: str, next_step: str) -> GovernedRunResult:
            blocked_goal = self.ledger.transition(
                current,
                GoalState.BLOCKED,
                evidence={"blocker": reason, "next_step": next_step},
            )
            return GovernedRunResult(
                blocked_goal,
                self.ledger.handoff(blocked_goal, required_gate=gate),
                reason,
            )

        if preflight.status is not PreflightStatus.PASS:
            return blocked(goal, "; ".join(preflight.reasons), "preflight", "refresh source evidence")
        try:
            current = self.ledger.transition(goal, GoalState.PROPOSED)
            current = self.ledger.transition(current, GoalState.APPROVED, preflight=preflight)
            current = self.ledger.transition(current, GoalState.PLANNED, preflight=preflight)
            current = self.ledger.transition(current, GoalState.BUILDING, preflight=preflight)
            evidence = dict(build())
            if not evidence.get("tests"):
                return blocked(current, "build returned no test evidence", "tests", "run targeted tests")
            current = self.ledger.transition(current, GoalState.VERIFIED, preflight=preflight, evidence=evidence)
            review_result = review(evidence)
            if not isinstance(review_result, ReviewEvidence):
                return blocked(
                    current,
                    "review evidence must include matching diff_id and reviewer",
                    "reviewer",
                    "return ReviewEvidence with non-empty diff_id and reviewer",
                )
            verdict = review_result.verdict
            expected_diff = str(evidence.get("diff_id", ""))
            if not expected_diff or not review_result.diff_id or not review_result.reviewer:
                return blocked(
                    current,
                    "review evidence has missing diff_id or reviewer",
                    "reviewer",
                    "return complete ReviewEvidence",
                )
            if review_result.diff_id != expected_diff:
                return blocked(
                    current,
                    f"review diff mismatch: expected {expected_diff}, got {review_result.diff_id}",
                    "reviewer",
                    "review the current diff",
                )
            if verdict is not ReviewVerdict.PASS:
                return blocked(current, f"review verdict: {verdict.value}", "reviewer", "address review findings")
            if prelanding_evidence is None:
                return blocked(current, "prelanding DoD evidence missing", "postcommit", "prepare and verify DoD evidence before landing")
            done, missing = DefinitionOfDone().evaluate(prelanding_evidence)
            if not done:
                return blocked(current, "prelanding DoD incomplete: " + ", ".join(missing), "postcommit", "complete DoD before landing")
            landing_evidence = landing(evidence)
            current = self.ledger.transition(
                current,
                GoalState.LANDED,
                review=verdict,
                review_evidence=review_result,
                landing_evidence=landing_evidence,
                evidence={"commit": landing_evidence.commit},
            )
            return GovernedRunResult(current)
        except Exception as exc:
            return blocked(goal, f"runner exception: {type(exc).__name__}: {exc}", "runner", "inspect and retry")
