"""Observe-only tick over the governed Faber backlog.

The goal registry had no caller: goals could be promoted into it and nothing
would ever look at them, so the queue's state was only knowable by hand.  This
module closes that without granting any new authority — it reads the backlog,
measures the evidence that is actually available, runs the same
:class:`PreflightGate` and owner-gate rules the runner uses, and records the
verdict.

It deliberately cannot build, review, commit, land, or start anything.  There is
no build callback to invoke and :class:`GovernedCodeRunner` is never constructed
here.  Wiring an *executing* tick is BL-3633's own scope and needs its own gate;
this one only makes the queue observable, so a goal that is stuck is visible as
stuck instead of silently absent.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.code_workflow import (
    _SELF_CLEARING_GATES,
    FaberGoal,
    FaberGoalRegistry,
    PreflightGate,
    PreflightInput,
    PreflightStatus,
)

#: Statuses PreflightGate treats as actionable.  Mirrored here only to explain a
#: BLOCK in the readback; the gate itself remains the single decision point.
_UNKNOWN = "unknown"


@dataclass(frozen=True)
class GoalObservation:
    """What one goal's evidence actually says right now."""

    goal_id: str
    bl_ref: str
    gate: str
    state: str
    preflight: str
    stopped_by: str
    reasons: tuple[str, ...] = ()
    next_step: str = ""


@dataclass(frozen=True)
class ObserveResult:
    observed_at: str
    registry: str
    goals: int
    runnable: int
    observations: tuple[GoalObservation, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "registry": self.registry,
            "goals": self.goals,
            "runnable": self.runnable,
            "action_taken": (
                "Read the governed backlog and evaluated preflight and the owner gate. "
                "No build, review, commit, landing, ACT, or service start was attempted — "
                "this tick has no capability to perform any of them."
            ),
            "observations": [
                {
                    "goal_id": o.goal_id,
                    "bl_ref": o.bl_ref,
                    "gate": o.gate,
                    "state": o.state,
                    "preflight": o.preflight,
                    "stopped_by": o.stopped_by,
                    "reasons": list(o.reasons),
                    "next_step": o.next_step,
                }
                for o in self.observations
            ],
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_is_clean(repo: str | os.PathLike[str] | None) -> bool:
    """Measure the target tree rather than assuming it.

    An unreachable or non-git path is reported dirty: unknown is not clean.
    """
    if not repo:
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and not proc.stdout.strip()


def evidence_for(goal: FaberGoal, *, git_clean: bool) -> PreflightInput:
    """Build the goal's preflight input from what it actually recorded.

    Nothing is upgraded on the way in: a status the goal never established stays
    unknown, so the gate blocks for a reason that names the missing evidence.
    """
    ev = goal.evidence
    # PreflightGate requires an authoritative reference per source.  They are
    # read only from fields a governance step actually recorded -- a goal that
    # never established one is missing it, and the gate names it in the BLOCK.
    refs = {}
    for name, value in (
        ("git", ev.get("git_ref", "")),
        ("lease", ev.get("lease_ref", "")),
        ("cad", goal.cad_ref),
        ("adr", goal.adr_ref),
        ("bl", goal.bl_ref),
        ("obsidian", ev.get("obsidian_ref", "")),
    ):
        if str(value).strip():
            refs[name] = str(value)
    return PreflightInput(
        git_clean=git_clean,
        lease_clear=str(ev.get("lease", "")).strip().lower() == "clear",
        cad_status=str(ev.get("cad_status", _UNKNOWN)),
        adr_status=str(ev.get("adr_status", _UNKNOWN)),
        bl_status=str(ev.get("bl_status", _UNKNOWN)),
        obsidian_status=str(ev.get("obsidian_status", _UNKNOWN)),
        source_refs=refs,
    )


def observe_goal(goal: FaberGoal, *, git_clean: bool, gate: PreflightGate) -> GoalObservation:
    """Evaluate one goal without touching it."""
    result = gate.evaluate(evidence_for(goal, git_clean=git_clean))
    owner_gate = str(goal.evidence.get("gate", "")).strip().lower()
    needs_owner = (
        owner_gate not in _SELF_CLEARING_GATES
        and not str(goal.evidence.get("owner_approval", "")).strip()
    )
    if result.status is not PreflightStatus.PASS:
        stopped_by = "preflight"
    elif needs_owner:
        stopped_by = "owner_gate"
    else:
        stopped_by = "none"
    return GoalObservation(
        goal_id=goal.goal_id,
        bl_ref=goal.bl_ref,
        gate=owner_gate or "(unset)",
        state=goal.state.value,
        preflight=result.status.value,
        stopped_by=stopped_by,
        reasons=result.reasons,
        next_step=goal.next_step,
    )


def observe(
    registry: FaberGoalRegistry,
    *,
    repo_paths: Mapping[str, str] | None = None,
) -> ObserveResult:
    """Read the whole backlog and report what each goal is waiting for."""
    gate = PreflightGate()
    clean_cache: dict[str, bool] = {}
    observations = []
    for goal in sorted(registry.all(), key=lambda g: (g.bl_ref, g.goal_id)):
        repo = (repo_paths or {}).get(goal.goal_id, "")
        if repo not in clean_cache:
            clean_cache[repo] = git_is_clean(repo)
        observations.append(observe_goal(goal, git_clean=clean_cache[repo], gate=gate))
    return ObserveResult(
        observed_at=_now(),
        registry=str(registry.path) if registry.path else "(memory)",
        goals=len(observations),
        runnable=sum(1 for o in observations if o.stopped_by == "none"),
        observations=tuple(observations),
    )


def record(result: ObserveResult, path: str | os.PathLike[str]) -> Path:
    """Append the tick to a durable trail and refresh the latest readback."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.to_json(), ensure_ascii=False)
    with open(target.with_suffix(".jsonl"), "a", encoding="utf-8") as handle:
        handle.write(payload + "\n")
    target.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one observe-only tick over the governed Faber backlog. Never builds or lands."
    )
    parser.add_argument(
        "--registry",
        default=os.path.join(os.environ.get("HERMES_HOME", ""), "faber", "goals.json"),
        help="Faber goal registry (default: $HERMES_HOME/faber/goals.json)",
    )
    parser.add_argument("--record", help="Write the readback here (a .jsonl trail is kept alongside)")
    parser.add_argument("--repo", action="append", default=[], metavar="GOAL_ID=PATH",
                        help="Measure git cleanliness for a goal's target tree (repeatable)")
    args = parser.parse_args(argv)
    registry_path = args.registry
    if not registry_path or registry_path.startswith(os.sep + "faber"):
        print(json.dumps({"status": "BLOCK", "reasons": ["--registry is required (HERMES_HOME is unset)"]}))
        return 2
    repo_paths = {}
    for item in args.repo:
        goal_id, _, path = item.partition("=")
        if not goal_id or not path:
            print(json.dumps({"status": "BLOCK", "reasons": [f"--repo expects GOAL_ID=PATH, got {item!r}"]}))
            return 2
        repo_paths[goal_id] = path
    result = observe(FaberGoalRegistry(os.path.expanduser(registry_path)), repo_paths=repo_paths)
    if args.record:
        record(result, args.record)
    print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
