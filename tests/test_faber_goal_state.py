"""Tests for faber_goal_state (BL-4006).

The interesting ones are the guard and contract tests: this module is only
useful if it CANNOT become the thing that opens a gate, and only trustworthy if
it cannot lose history quietly.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agent import faber_goal_state as gs


# ---------------------------------------------------------------- positive ---

def test_first_observation_starts_at_seq_one():
    doc, out = gs.record("g1", phase="preflight", outcome="BLOCK", reasons=["a"], doc={"goals": {}})
    assert out.seq == 1
    assert out.changed is True
    assert out.unchanged_ticks == 0
    assert doc["goals"]["g1"]["first_seen_at"]
    assert len(doc["goals"]["g1"]["history"]) == 1


def test_seq_is_monotonic_within_a_journal_generation():
    doc = {"goals": {}}
    seqs = []
    for i in range(5):
        doc, out = gs.record("g1", phase="preflight", outcome="BLOCK",
                             reasons=[f"r{i}"], doc=doc)
        seqs.append(out.seq)
    assert seqs == [1, 2, 3, 4, 5] == sorted(seqs)


# --------------------------------------------------------------- unchanged ---

def test_identical_refusal_counts_but_does_not_grow_history():
    """The activation-todo.log defect: 338 lines, one fact. Count, don't re-list."""
    doc = {"goals": {}}
    doc, _ = gs.record("g1", phase="preflight", outcome="BLOCK", reasons=["x"], doc=doc)
    first_change = doc["goals"]["g1"]["last_change_at"]
    for _ in range(10):
        doc, out = gs.record("g1", phase="preflight", outcome="BLOCK", reasons=["x"], doc=doc)
    entry = doc["goals"]["g1"]
    assert out.changed is False
    assert entry["unchanged_ticks"] == 10
    assert len(entry["history"]) == 1, "unchanged observations must not be re-listed"
    assert entry["last_change_at"] == first_change, "last_change_at must not move on no-change"
    assert entry["seq"] == 11, "seq still advances — the tick DID happen"


def test_changed_refusal_resets_counter_and_appends_history():
    doc = {"goals": {}}
    doc, _ = gs.record("g1", phase="preflight", outcome="BLOCK", reasons=["x"], doc=doc)
    doc, _ = gs.record("g1", phase="preflight", outcome="BLOCK", reasons=["x"], doc=doc)
    assert doc["goals"]["g1"]["unchanged_ticks"] == 1
    doc, out = gs.record("g1", phase="preflight", outcome="BLOCK", reasons=["y"], doc=doc)
    assert out.changed is True
    assert doc["goals"]["g1"]["unchanged_ticks"] == 0
    assert len(doc["goals"]["g1"]["history"]) == 2


def test_fingerprint_change_alone_counts_as_changed():
    """Structured state can move while the prose stays identical."""
    doc = {"goals": {}}
    doc, _ = gs.record("g1", phase="p", outcome="BLOCK", reasons=["same"],
                       fingerprint={"state": "candidate"}, doc=doc)
    doc, out = gs.record("g1", phase="p", outcome="BLOCK", reasons=["same"],
                         fingerprint={"state": "approved"}, doc=doc)
    assert out.changed is True, "a structured change must not read as unchanged"


# ------------------------------------------------------------------ digest ---

def test_digest_is_order_insensitive_and_whitespace_normalised():
    a = gs.reason_digest(["alpha", "beta"])
    b = gs.reason_digest(["beta", "alpha"])
    c = gs.reason_digest(["  alpha  ", "beta\n"])
    assert a == b == c


def test_digest_separator_prevents_join_collision():
    """With a space separator, ["a b"] and ["a","b"] would collide."""
    assert gs.reason_digest(["a b"]) != gs.reason_digest(["a", "b"])


# ------------------------------------------------------------------ guards ---

def test_empty_goal_id_is_rejected():
    with pytest.raises(ValueError):
        gs.record("   ", phase="p", outcome="o", doc={"goals": {}})


def test_missing_file_is_an_empty_journal_not_an_error(tmp_path: Path):
    doc = gs.load(tmp_path / "nope.json")
    assert doc["goals"] == {}
    assert "unreadable" not in doc


def test_corrupt_file_is_reported_not_silently_empty(tmp_path: Path):
    p = tmp_path / "goal-state.json"
    p.write_text("{ this is not json", encoding="utf-8")
    doc = gs.load(p)
    assert doc["goals"] == {}
    assert doc.get("unreadable") == str(p), "a corrupt journal must not look like an empty one"


def test_malformed_shape_is_reported(tmp_path: Path):
    p = tmp_path / "goal-state.json"
    p.write_text(json.dumps({"goals": ["not", "a", "dict"]}), encoding="utf-8")
    assert gs.load(p).get("malformed") == str(p)


# ------------------------------------------------- corruption is fail-closed ---

def test_corrupt_journal_is_quarantined_and_not_overwritten(tmp_path: Path):
    """Overwriting an unreadable journal turns recoverable corruption into a
    silent history reset — the exact defect class this module exists to find."""
    target = tmp_path / "goal-state.json"
    gs.record_all([{"goal_id": "g1", "preflight": "BLOCK", "reasons": ["x"]}], path=target)
    target.write_text("{ corrupted", encoding="utf-8")

    res = gs.record_all([{"goal_id": "g1", "preflight": "BLOCK", "reasons": ["x"]}], path=target)

    assert res["status"] == "BLOCK"
    assert res["recorded"] == 0
    quarantined = Path(res["quarantined_to"])
    assert quarantined.exists(), "the damaged journal must be preserved"
    assert quarantined.read_text(encoding="utf-8") == "{ corrupted"
    assert not target.exists(), "a journal we could not read must not be replaced"


def test_corrupt_journal_never_silently_restarts_seq(tmp_path: Path):
    target = tmp_path / "goal-state.json"
    for _ in range(5):
        gs.record_all([{"goal_id": "g1", "preflight": "BLOCK", "reasons": ["x"]}], path=target)
    assert gs.load(target)["goals"]["g1"]["seq"] == 5

    target.write_text("{ corrupted", encoding="utf-8")
    res = gs.record_all([{"goal_id": "g1", "preflight": "BLOCK", "reasons": ["x"]}], path=target)
    assert res["status"] == "BLOCK"
    # The tick refused, so no fresh journal was written at all.
    assert not target.exists()


# --------------------------------------------------------- phantom ticks -----

def test_unchanged_source_snapshot_is_a_noop(tmp_path: Path):
    """Re-running against the same observe-last.json must not invent a tick."""
    target = tmp_path / "goal-state.json"
    obs = [{"goal_id": "g1", "preflight": "BLOCK", "reasons": ["x"]}]

    first = gs.record_all(obs, path=target, observed_at="2026-08-10T14:00:01Z")
    assert first["status"] == "EXECUTED"

    again = gs.record_all(obs, path=target, observed_at="2026-08-10T14:00:01Z")
    assert again["status"] == "SKIPPED"
    assert again["recorded"] == 0
    assert gs.load(target)["goals"]["g1"]["seq"] == 1, "seq must not advance on a phantom tick"
    assert gs.load(target)["goals"]["g1"]["unchanged_ticks"] == 0

    moved = gs.record_all(obs, path=target, observed_at="2026-08-10T14:20:01Z")
    assert moved["status"] == "EXECUTED"
    assert gs.load(target)["goals"]["g1"]["unchanged_ticks"] == 1


# ------------------------------------------------------------ no silent cap ---

def test_history_truncation_is_reported_per_tick_and_accumulated(tmp_path: Path):
    doc = {"goals": {}}
    for i in range(gs.HISTORY_LIMIT + 5):
        doc, out = gs.record("g1", phase="preflight", outcome="BLOCK",
                             reasons=[f"reason-{i}"], doc=doc)
    entry = doc["goals"]["g1"]
    assert len(entry["history"]) == gs.HISTORY_LIMIT
    assert out.dropped_history == 1, "each truncating write must report what it dropped"
    assert entry["dropped_history_total"] == 5, "the cumulative loss must stay recoverable"


def test_summary_reports_total_not_the_capped_count():
    doc = {"goals": {}}
    for i in range(gs.HISTORY_LIMIT + 5):
        doc, _ = gs.record("g1", phase="p", outcome="BLOCK", reasons=[f"r{i}"], doc=doc)
    row = gs.summarise(doc)["rows"][0]
    assert row["history_retained"] == gs.HISTORY_LIMIT
    assert row["history_dropped"] == 5
    assert row["history_total"] == gs.HISTORY_LIMIT + 5


def test_blank_goal_id_is_counted_not_silently_dropped(tmp_path: Path):
    res = gs.record_all(
        [{"goal_id": "a", "preflight": "BLOCK"}, {"goal_id": "  ", "preflight": "BLOCK"}],
        path=tmp_path / "gs.json",
    )
    assert res["recorded"] == 1
    assert res["skipped_without_goal_id"] == 1


# ---------------------------------------------------------------- contract ---

def test_module_exposes_no_gate_verdict():
    """Tripwire, not a proof: a name blacklist cannot catch every phrasing.
    The mechanically strong guard is the import-direction test below."""
    forbidden = {"passes", "is_clear", "authorise", "authorize", "allow",
                 "grant", "preflight", "evaluate", "verdict", "unblock"}
    public = {n for n in dir(gs) if not n.startswith("_")}
    assert not (public & forbidden), f"journal must not expose gate verbs: {public & forbidden}"


def test_summary_records_an_observed_pass_but_issues_no_verdict():
    """Recording an OBSERVED outcome is the job; issuing one is forbidden.

    An earlier version asserted the substring "pass" was absent — which would
    have failed the first time a goal legitimately cleared preflight, i.e. at
    exactly the moment BL-4003 succeeds. The pressure then would be to delete
    the contract test.
    """
    doc = {"goals": {}}
    doc, _ = gs.record("g1", phase="none", outcome="PASS", reasons=[], doc=doc)
    s = gs.summarise(doc)
    assert s["rows"][0]["outcome"] == "PASS"
    assert not (set(s) & {"pass", "passes", "clear", "authorised", "allowed", "verdict"})
    assert "journal, not evidence" in s["note"].lower()


def test_gate_modules_do_not_import_the_journal():
    """THE contract guard: evidence must not be able to flow from journal to gate.

    Name blacklists miss creative phrasings; an import edge is mechanical. If
    code_workflow or faber_observe ever imports this module, the gate is one
    line away from reading a file the producer writes (BL-3673, cab10c5f9).

    LIMITS, stated here because this is where someone modifying the guard reads:
    it is STATIC, so a dynamic ``importlib.import_module("agent.faber_goal_state")``
    slips past, as does a consumer that simply opens ``goal-state.json`` and
    derives a verdict from it. Those two cannot be caught from this side.
    """
    here = Path(gs.__file__).resolve().parent
    checked = 0
    for name in ("code_workflow.py", "faber_observe.py"):
        src = here / name
        if not src.exists():
            continue
        checked += 1
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(a.name for a in node.names)
        assert not any("faber_goal_state" in m for m in imported), (
            f"{name} must never import the journal — it is not evidence"
        )
    # A skip reads as a pass. If both gate modules are renamed or moved, this
    # guard would silently stop guarding — absence wearing success's costume,
    # which is the exact defect class this BL is about.
    assert checked > 0, "no gate module found to check — the guard is not guarding"


# --------------------------------------------------------------- migration ---

def _pre_bl4006_entry(unchanged_ticks: int = 337, last_change: str = "2026-07-01T00:00:00Z"):
    """An entry as the previous version wrote it: no ``fingerprint`` key."""
    digest = gs.reason_digest(["same reason"])
    return {
        "goals": {
            "g1": {
                "seq": unchanged_ticks + 1,
                "phase": "preflight",
                "outcome": "BLOCK",
                "reason_digest": digest,
                "reasons": ["same reason"],
                "first_seen_at": last_change,
                "last_change_at": last_change,
                "last_observed_at": last_change,
                "unchanged_ticks": unchanged_ticks,
                "history": [{"seq": 1, "at": last_change, "phase": "preflight",
                             "outcome": "BLOCK", "digest": digest}],
            }
        }
    }


def test_migration_does_not_spend_the_streak():
    """A SCHEMA change is not a WORLD change.

    A goal refused identically since 1 July must not report a fresh change just
    because the journal gained a field — that would make the module's headline
    sentence false for every goal at the moment it starts being trusted.
    """
    doc = _pre_bl4006_entry()
    doc, out = gs.record("g1", phase="preflight", outcome="BLOCK",
                         reasons=["same reason"], fingerprint={"gate": "reviewer"}, doc=doc)
    entry = doc["goals"]["g1"]
    assert out.changed is False, "a backfill must not be reported as a change"
    assert out.migrated is True
    assert entry["unchanged_ticks"] == 338, "the streak is the asset — it must survive"
    assert entry["last_change_at"] == "2026-07-01T00:00:00Z", "last_change_at must not move"
    assert entry["fingerprint"] == {"gate": "reviewer"}, "the field must still be backfilled"


def test_migration_is_counted_apart_from_real_changes(tmp_path: Path):
    target = tmp_path / "goal-state.json"
    target.write_text(json.dumps(_pre_bl4006_entry()), encoding="utf-8")
    res = gs.record_all(
        [{"goal_id": "g1", "stopped_by": "preflight", "preflight": "BLOCK",
          "reasons": ["same reason"], "gate": "reviewer"}],
        path=target,
    )
    assert res["changed_count"] == 0, "a migration must never inflate changed_count"
    assert res["migrated_count"] == 1


def test_real_change_after_migration_is_still_detected():
    """The backfill must not desensitise the entry to genuine movement."""
    doc = _pre_bl4006_entry()
    doc, _ = gs.record("g1", phase="preflight", outcome="BLOCK",
                       reasons=["same reason"], fingerprint={"gate": "reviewer"}, doc=doc)
    doc, out = gs.record("g1", phase="preflight", outcome="BLOCK",
                         reasons=["same reason"], fingerprint={"gate": "morten"}, doc=doc)
    assert out.changed is True and out.migrated is False
    assert doc["goals"]["g1"]["unchanged_ticks"] == 0


# --------------------------------------------------------------- aggregate ---

def test_never_changed_surfaces_a_permanently_stuck_goal():
    """The headline signal: a gate whose PASS condition has never been reached."""
    doc = {"goals": {}}
    for _ in range(50):
        doc, _ = gs.record("stuck", phase="preflight", outcome="BLOCK",
                           reasons=["same"], doc=doc)
    doc, _ = gs.record("moving", phase="preflight", outcome="BLOCK", reasons=["a"], doc=doc)
    doc, _ = gs.record("moving", phase="design", outcome="PASS", reasons=[], doc=doc)

    s = gs.summarise(doc)
    assert s["never_changed"] == ["stuck"]
    assert s["never_changed_count"] == 1
    assert s["max_unchanged_ticks"] == 49


# -------------------------------------------------------------- round-trip ---

def test_record_all_round_trips_through_disk(tmp_path: Path):
    target = tmp_path / "faber" / "goal-state.json"
    observations = [
        {"goal_id": "a", "stopped_by": "preflight", "preflight": "BLOCK", "reasons": ["r1"]},
        {"goal_id": "b", "stopped_by": "preflight", "preflight": "BLOCK", "reasons": ["r2"]},
    ]
    res = gs.record_all(observations, path=target)
    assert res["recorded"] == 2 and res["changed_count"] == 2 and target.exists()

    again = gs.record_all(observations, path=target)
    assert again["changed_count"] == 0, "a repeat tick changes nothing"

    doc = gs.load(target)
    assert doc["goals"]["a"]["unchanged_ticks"] == 1
    assert doc["goals"]["a"]["seq"] == 2


def test_write_is_atomic_no_partial_file_left_behind(tmp_path: Path):
    target = tmp_path / "goal-state.json"
    gs.record_all([{"goal_id": "a", "preflight": "BLOCK", "reasons": ["x"]}], path=target)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".goal-state.")]
    assert leftovers == [], f"temp files must be renamed away, found {leftovers}"
    assert json.loads(target.read_text(encoding="utf-8"))["goals"]["a"]["seq"] == 1
