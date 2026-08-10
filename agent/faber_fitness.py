"""faber_fitness.py — architecture fitness for the governed workflow (BL-4029 L9).

THE INVARIANT
-------------
**No gate may exist whose PASS condition has never been reached.**

A gate that has never passed is indistinguishable, from the outside, from a gate
that is working perfectly and simply has nothing to admit.  The difference is
only visible over TIME, and only if someone counts.

BL-4003 is the worked example: ``preflight_clear: 0`` of 7, unchanged across
340 consecutive samples, every one of them truthful.  Each line was correct.
Nobody read line 200.  The system was honest and dead at the same time, and
honesty was not the point -- **a truthful line printed 338 times is exactly as
dead as a false green.**  From the fabric's side (measure -> :DriftAlert ->
triage -> ROI) both are silence.

This module is the thing that would have caught that automatically, on day one,
without a human reading a log.

WHY IT IS SEPARATE FROM THE JOURNAL
-----------------------------------
``faber_goal_state`` (BL-4006) counts.  This judges.  The split is deliberate:
the journal must stay a journal -- if it could raise an alert it would be one
step from being read as evidence, which is the defect BL-3673 caught.  This
module reads the journal and never writes it.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not write to the graph.  ADR-061's credential boundary keeps graph
credentials off ``.15``, so emitting a ``:DriftAlert`` needs the authority path
(BL-4029 L5).  Until that exists this emits a verdict and a non-zero exit code,
which a caller can route.  **That is a real limitation, not a design choice** --
stated here so nobody mistakes a verdict file for fabric integration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

#: Observations of a goal whose recorded outcome never once differed before the
#: gate is called dead rather than merely quiet.  20 ticks at the observe
#: cadence of 20 minutes is a little under 7 hours -- long enough that a slow
#: but living chain is not accused, short enough to fire within a working day.
DEAD_GATE_TICKS = 20

#: Consecutive identical observations of a SINGLE goal before it is flagged.
#: Higher than DEAD_GATE_TICKS because one stuck goal is ordinary; a whole gate
#: that has never admitted anything is not.
STUCK_GOAL_TICKS = 40


#: Outcome strings that count as the gate ADMITTING something. Anything else --
#: including a changed refusal reason -- is movement, not admission.
_PASSING_OUTCOMES = frozenset({"PASS", "GO_READ_ONLY", "GO_ISOLATED_WRITE"})


class Verdict:
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Finding:
    check: str
    verdict: str
    detail: str
    evidence: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "verdict": self.verdict,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check_gate_has_ever_passed(summary: dict[str, Any]) -> Finding:
    """THE headline check: has this gate ever admitted anything?

    ``never_changed`` counts goals whose recorded outcome has never differed
    since first observation.  If that is EVERY goal, and they have been watched
    long enough, the gate has no demonstrated PASS path at all.
    """
    goals = int(summary.get("goals", 0) or 0)
    never = int(summary.get("never_changed_count", 0) or 0)
    max_unchanged = int(summary.get("max_unchanged_ticks", 0) or 0)
    ev = {"goals": goals, "never_changed_count": never, "max_unchanged_ticks": max_unchanged,
          "threshold_ticks": DEAD_GATE_TICKS}

    # BL-4029 L9, corrected: an earlier version of this check was NAMED
    # "has ever passed" and MEASURED "has ever changed". Measured 2026-08-10,
    # right after L4 landed: all 7 goals changed (their refusal reasons moved)
    # while preflight_clear stayed 0 -- and the check reported PASS. A gate
    # whose refusals churn but which never admits anything is exactly the
    # failure this module exists to catch, so churn must never count as health.
    passing = sorted({str(o).upper() for row in (summary.get("rows") or [])
                      for o in (row.get("outcomes_seen") or [])} & _PASSING_OUTCOMES)
    ev["passing_outcomes_seen"] = passing

    if goals == 0:
        # Absence is reported as absence, never as health.
        return Finding("gate_has_ever_passed", Verdict.WARN,
                       "no goals recorded — the gate cannot be judged, and that is "
                       "not the same as the gate being fine", ev)
    if passing:
        return Finding("gate_has_ever_passed", Verdict.PASS,
                       f"a PASS outcome has been observed: {', '.join(passing)}", ev)
    if never < goals and max_unchanged < DEAD_GATE_TICKS:
        return Finding("gate_has_ever_passed", Verdict.WARN,
                       f"goals are moving but none has PASSED yet — {goals - never} of {goals} "
                       f"changed. Movement is not admission.", ev)
    if max_unchanged < DEAD_GATE_TICKS and never >= goals:
        return Finding("gate_has_ever_passed", Verdict.WARN,
                       f"no goal has ever moved, but only {max_unchanged} observations so far "
                       f"(threshold {DEAD_GATE_TICKS}) — quiet, not yet proven dead", ev)
    return Finding(
        "gate_has_ever_passed", Verdict.FAIL,
        f"NO gate PASS has ever been observed across {goals} goals "
        f"(longest unchanged streak {max_unchanged} observations). A gate whose PASS "
        f"condition has never been reached is not fail-closed — it is closed.", ev)


def check_individual_stuck_goals(summary: dict[str, Any]) -> list[Finding]:
    """Per-goal staleness. One stuck goal is ordinary; naming it is still useful."""
    out: list[Finding] = []
    for row in summary.get("rows") or []:
        ticks = int(row.get("unchanged_ticks", 0) or 0)
        if ticks >= STUCK_GOAL_TICKS:
            out.append(Finding(
                "goal_not_progressing", Verdict.WARN,
                f"{row.get('goal_id')} unchanged for {ticks} observations "
                f"(phase={row.get('phase')}, outcome={row.get('outcome')})",
                {"goal_id": row.get("goal_id"), "unchanged_ticks": ticks,
                 "last_change_at": row.get("last_change_at"),
                 "threshold_ticks": STUCK_GOAL_TICKS}))
    return out


def check_journal_is_being_written(summary: dict[str, Any]) -> Finding:
    """A fitness check that reads a stale file reports the past as the present.

    This is the self-check: if the journal itself stopped being written, every
    other finding here is about a world that no longer exists.
    """
    src = summary.get("source_observed_at")
    ev = {"source_observed_at": src}
    if not src:
        return Finding("journal_is_current", Verdict.WARN,
                       "journal carries no source_observed_at — cannot tell whether the "
                       "findings above describe now or last week", ev)
    return Finding("journal_is_current", Verdict.PASS, f"journal sourced at {src}", ev)


def evaluate(summary: dict[str, Any]) -> dict[str, Any]:
    findings = [check_gate_has_ever_passed(summary), check_journal_is_being_written(summary)]
    findings.extend(check_individual_stuck_goals(summary))
    worst = Verdict.PASS
    for f in findings:
        if f.verdict == Verdict.FAIL:
            worst = Verdict.FAIL
            break
        if f.verdict == Verdict.WARN:
            worst = Verdict.WARN
    return {
        "artifact": "faber-fitness-v1",
        "checked_at": _now(),
        "verdict": worst,
        "invariant": "no gate may exist whose PASS condition has never been reached",
        "findings": [f.to_json() for f in findings],
        "not_wired_to_fabric": (
            "This emits a verdict only. Writing a :DriftAlert needs the authority path "
            "(BL-4029 L5) because ADR-061 keeps graph credentials off .15."
        ),
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Architecture fitness for the governed workflow. "
                    "Invariant: no gate may exist whose PASS condition has never been reached.")
    ap.add_argument("--summary-json", default=None,
                    help="path to a faber_goal_state --summary payload (default: read the journal)")
    ap.add_argument("--record", default=None, help="write the verdict here")
    args = ap.parse_args(argv)

    if args.summary_json:
        p = Path(args.summary_json)
        if not p.exists():
            print(json.dumps({"verdict": "FAIL", "reason": f"missing {p}"}), file=sys.stderr)
            return 2
        summary = json.loads(p.read_text(encoding="utf-8"))
    else:
        try:
            from agent import faber_goal_state as gs
        except ImportError as exc:
            print(json.dumps({"verdict": "FAIL", "reason": f"journal unavailable: {exc}"}),
                  file=sys.stderr)
            return 2
        summary = gs.summarise(gs.load())

    result = evaluate(summary)
    blob = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    print(blob)
    if args.record:
        target = Path(args.record)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(blob + "\n", encoding="utf-8")

    # A FAIL must be loud even when a caller discards stdout.
    if result["verdict"] == Verdict.FAIL:
        print(blob, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
