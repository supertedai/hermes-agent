"""Tests for faber_fitness (BL-4029 L9).

The load-bearing one is test_the_bl4003_situation_is_caught: this module only
earns its place if it would have fired on the defect it was written for.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent import faber_fitness as ff


def _summary(*, goals, never, max_unchanged, rows=None, observed_at="2026-08-10T17:20:01Z"):
    return {
        "goals": goals,
        "never_changed_count": never,
        "max_unchanged_ticks": max_unchanged,
        "source_observed_at": observed_at,
        "rows": rows or [],
    }


# ------------------------------------------------------------------ headline ---

def test_the_bl4003_situation_is_caught():
    """The whole reason this module exists.

    Measured reality on 2026-08-10: 7 goals, none ever moved, 340 identical
    samples. Every line truthful, nobody reading. If this does not FAIL, the
    module is decoration.
    """
    r = ff.evaluate(_summary(goals=7, never=7, max_unchanged=340))
    assert r["verdict"] == ff.Verdict.FAIL
    headline = [f for f in r["findings"] if f["check"] == "gate_has_ever_passed"][0]
    assert headline["verdict"] == ff.Verdict.FAIL
    assert "never been reached" in headline["detail"]


def test_a_gate_that_admits_something_passes():
    """PASS requires an observed PASSING OUTCOME -- not merely a goal that moved."""
    rows = [{"goal_id": "g", "unchanged_ticks": 1, "outcomes_seen": ["BLOCK", "PASS"]}]
    r = ff.evaluate(_summary(goals=7, never=6, max_unchanged=340, rows=rows))
    headline = [f for f in r["findings"] if f["check"] == "gate_has_ever_passed"][0]
    assert headline["verdict"] == ff.Verdict.PASS
    assert "PASS" in headline["evidence"]["passing_outcomes_seen"]


def test_churn_without_admission_is_not_health():
    """BL-4029 L9, the correction that earned its own test.

    An earlier version of this module was NAMED gate_has_ever_passed and
    MEASURED has_ever_changed. Measured live right after L4 landed: all 7 goals
    changed -- their refusal reasons moved -- while preflight_clear stayed 0,
    and the check reported PASS. A gate whose refusals churn but which never
    admits anything is precisely the failure this module exists to catch.

    Movement is not admission.
    """
    rows = [{"goal_id": f"g{i}", "unchanged_ticks": 0,
             "outcomes_seen": ["BLOCK"]} for i in range(7)]
    r = ff.evaluate(_summary(goals=7, never=0, max_unchanged=999, rows=rows))
    headline = [f for f in r["findings"] if f["check"] == "gate_has_ever_passed"][0]
    assert headline["verdict"] == ff.Verdict.FAIL, \
        "goals changing their refusal reason must never read as the gate passing"
    assert headline["evidence"]["passing_outcomes_seen"] == []


def test_early_churn_is_warned_not_failed():
    """Before the dead-gate threshold, churn without admission is a warning."""
    rows = [{"goal_id": "g", "unchanged_ticks": 0, "outcomes_seen": ["BLOCK"]}]
    r = ff.evaluate(_summary(goals=7, never=0, max_unchanged=3, rows=rows))
    headline = [f for f in r["findings"] if f["check"] == "gate_has_ever_passed"][0]
    assert headline["verdict"] == ff.Verdict.WARN
    assert "Movement is not admission" in headline["detail"]


def test_quiet_is_not_yet_dead():
    """A young journal must not be accused. Absence of movement early is
    indistinguishable from a healthy gate with nothing to admit."""
    r = ff.evaluate(_summary(goals=7, never=7, max_unchanged=ff.DEAD_GATE_TICKS - 1))
    headline = [f for f in r["findings"] if f["check"] == "gate_has_ever_passed"][0]
    assert headline["verdict"] == ff.Verdict.WARN
    assert "not yet proven dead" in headline["detail"]


def test_threshold_is_the_boundary_not_an_approximation():
    at = ff.evaluate(_summary(goals=1, never=1, max_unchanged=ff.DEAD_GATE_TICKS))
    below = ff.evaluate(_summary(goals=1, never=1, max_unchanged=ff.DEAD_GATE_TICKS - 1))
    assert at["verdict"] == ff.Verdict.FAIL
    assert below["verdict"] == ff.Verdict.WARN


# -------------------------------------------------------------------- guards ---

def test_no_goals_is_a_warning_never_a_pass():
    """Absence reported as absence. An empty journal must never read as health —
    that is the defect class this whole BL is about."""
    r = ff.evaluate(_summary(goals=0, never=0, max_unchanged=0))
    headline = [f for f in r["findings"] if f["check"] == "gate_has_ever_passed"][0]
    assert headline["verdict"] == ff.Verdict.WARN
    assert "not the same as the gate being fine" in headline["detail"]


def test_a_stale_journal_is_flagged_so_findings_are_not_read_as_current():
    """A fitness check reading a stale file reports the past as the present."""
    s = _summary(goals=7, never=6, max_unchanged=3)
    s.pop("source_observed_at")
    r = ff.evaluate(s)
    cur = [f for f in r["findings"] if f["check"] == "journal_is_current"][0]
    assert cur["verdict"] == ff.Verdict.WARN
    assert r["verdict"] == ff.Verdict.WARN


def test_individual_stuck_goal_is_named():
    rows = [{"goal_id": "g-stuck", "unchanged_ticks": ff.STUCK_GOAL_TICKS,
             "phase": "preflight", "outcome": "BLOCK", "last_change_at": "2026-07-01T00:00:00Z"},
            {"goal_id": "g-fine", "unchanged_ticks": 2, "phase": "preflight", "outcome": "BLOCK"}]
    r = ff.evaluate(_summary(goals=2, never=1, max_unchanged=ff.STUCK_GOAL_TICKS, rows=rows))
    named = [f for f in r["findings"] if f["check"] == "goal_not_progressing"]
    assert len(named) == 1
    assert named[0]["evidence"]["goal_id"] == "g-stuck"


def test_fail_dominates_warn():
    rows = [{"goal_id": "g", "unchanged_ticks": ff.STUCK_GOAL_TICKS, "phase": "p", "outcome": "B"}]
    r = ff.evaluate(_summary(goals=1, never=1, max_unchanged=999, rows=rows))
    assert r["verdict"] == ff.Verdict.FAIL


# ------------------------------------------------------------------ contract ---

def test_the_verdict_names_its_own_limitation():
    """The module must not let a verdict file be mistaken for fabric integration."""
    r = ff.evaluate(_summary(goals=7, never=6, max_unchanged=3))
    assert "not_wired_to_fabric" in r
    assert "L5" in r["not_wired_to_fabric"]


def test_module_does_not_write_the_journal():
    """Contract with BL-4006: this reads the journal and never writes it.
    A judge that can edit its own evidence is not a judge."""
    src = Path(ff.__file__).read_text(encoding="utf-8")
    for forbidden in ("record_all(", "_save(", "gs.record("):
        assert forbidden not in src, f"fitness must not write the journal: {forbidden}"


def test_cli_exits_nonzero_on_fail(tmp_path: Path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(_summary(goals=7, never=7, max_unchanged=340)), encoding="utf-8")
    out = tmp_path / "verdict.json"
    rc = ff._cli(["--summary-json", str(p), "--record", str(out)])
    assert rc == 1, "a dead gate must be loud in the exit code, not only in stdout"
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == ff.Verdict.FAIL


def test_cli_exits_zero_when_healthy(tmp_path: Path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(_summary(goals=7, never=0, max_unchanged=2)), encoding="utf-8")
    assert ff._cli(["--summary-json", str(p)]) == 0


def test_cli_blocks_on_missing_input(tmp_path: Path):
    assert ff._cli(["--summary-json", str(tmp_path / "nope.json")]) == 2
