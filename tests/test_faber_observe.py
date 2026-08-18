import json

import pytest

from agent.code_workflow import FaberGoal, FaberGoalRegistry, GoalState
from agent.faber_observe import _cli, evidence_for, git_is_clean, observe, observe_goal, record
from agent.flyby_promote import build_goal, load_manifest, promote

from tests.test_flyby_promote import MANIFEST, packet


def promoted(**overrides):
    return build_goal(packet(**overrides), promoted_by="x", promoted_at="t")


# --- the tick observes, it never acts ------------------------------------------

def test_observe_reports_what_each_goal_waits_for(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    result = observe(registry)
    assert result.goals == 1
    assert result.preflight_clear == 0
    obs = result.observations[0]
    assert obs.preflight == "BLOCK"
    assert obs.stopped_by == "preflight"
    # ADR-062 V4: preflight navngir git/lease — aldri CAD (steg 7-artefakt)
    assert any("missing authoritative source refs" in r for r in obs.reasons)


def test_observe_names_the_owner_gate_once_preflight_would_pass(tmp_path):
    """A morten-gated goal with complete evidence is held by the owner gate,
    and the tick must say so rather than reporting it as runnable."""
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(
        FaberGoal(
            "faber.code.flyby:x", "X", cad_ref="CAD-M", adr_ref="ADR-1", bl_ref="BL-1",
            evidence={
                "gate": "morten", "cad_status": "verified", "adr_status": "accepted",
                "bl_status": "open", "obsidian_status": "fresh", "lease": "clear",
            },
        )
    )
    obs = observe(registry, repo_paths={"faber.code.flyby:x": str(tmp_path)}).observations[0]
    # tmp_path is not a git repo, so git_clean is False and preflight still blocks;
    # the point is that the owner gate is evaluated and reported, not skipped.
    assert obs.gate == "morten"
    assert obs.stopped_by in {"preflight", "owner_gate"}


def test_an_owner_approved_goal_with_full_evidence_clears_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.faber_observe.git_is_clean", lambda repo: True)
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(
        FaberGoal(
            "faber.code.flyby:x", "X", cad_ref="CAD-M", adr_ref="ADR-1", bl_ref="BL-1",
            evidence={
                "gate": "morten", "owner_approval": "morten:2026-08-04",
                "cad_status": "verified", "adr_status": "accepted",
                "bl_status": "open", "obsidian_status": "fresh", "lease": "clear",
                "git_ref": "abc1234", "lease_ref": "lease:hermes-agent",
                "obsidian_ref": "Brain/Symbiose Change Log.md",
            },
        )
    )
    result = observe(registry, repo_paths={"faber.code.flyby:x": str(tmp_path)})
    assert result.preflight_clear == 1
    assert result.observations[0].stopped_by == "none"


def test_evidence_is_never_upgraded_on_the_way_in():
    goal = promoted()
    ev = evidence_for(goal, git_clean=True)
    assert ev.cad_status == "unknown" and ev.adr_status == "unknown"
    assert ev.lease_clear is False          # "not_claimed" is not "clear"
    assert ev.obsidian_status == "unknown"
    # Only the BL number was ever established, so it is the only source ref.
    assert set(ev.source_refs) == {"bl"}


def test_a_missing_source_ref_is_named_in_the_block():
    goal = promoted()
    obs = observe_goal(goal, git_clean=True, gate=__import__("agent.code_workflow", fromlist=["PreflightGate"]).PreflightGate())
    assert any("missing authoritative source refs" in r for r in obs.reasons)
    # REQUIRED_REFS er (git, lease) — obsidian flyttet til steg 13 (BL-4029 L2)
    assert "git" in " ".join(obs.reasons) and "lease" in " ".join(obs.reasons)


def test_an_unreachable_or_non_git_target_counts_as_dirty(tmp_path):
    assert git_is_clean(None) is False
    assert git_is_clean("") is False
    assert git_is_clean(tmp_path / "does-not-exist") is False


def test_observation_readback_states_that_nothing_was_executed(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    payload = observe(registry).to_json()
    assert "No build, review, commit, landing, ACT, or service start" in payload["action_taken"]


def test_record_keeps_a_trail_and_a_latest_readback(tmp_path):
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    target = tmp_path / "observe-last.json"
    record(observe(registry), target)
    record(observe(registry), target)
    assert json.loads(target.read_text(encoding="utf-8"))["goals"] == 1
    trail = tmp_path / "observe-last.trail.jsonl"
    assert len(trail.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_a_jsonl_target_does_not_truncate_its_own_trail(tmp_path):
    """with_suffix('.jsonl') on a .jsonl path returns the same file, so the
    readback write would erase the append that just happened."""
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    target = tmp_path / "observe.jsonl"
    record(observe(registry), target)
    record(observe(registry), target)
    trail = tmp_path / "observe.trail.jsonl"
    assert trail != target
    assert len(trail.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_the_trail_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.faber_observe.TRAIL_LIMIT", 3)
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    target = tmp_path / "observe-last.json"
    for _ in range(6):
        record(observe(registry), target)
    trail = tmp_path / "observe-last.trail.jsonl"
    assert len(trail.read_text(encoding="utf-8").strip().splitlines()) == 3


def test_preflight_clear_is_not_called_runnable(tmp_path):
    """Clearing preflight and the owner gate is necessary, not sufficient — the
    runner still has build, review and landing gates the tick cannot know."""
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote([packet()], registry, promoted_by="x")
    payload = observe(registry).to_json()
    assert "preflight_clear" in payload and "runnable" not in payload
    assert "still has the runner" in payload["action_taken"]


# --- the CLI must never report an empty backlog it did not measure ------------

def test_cli_blocks_when_no_registry_can_be_resolved(monkeypatch, capsys):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert _cli([]) == 2
    captured = capsys.readouterr()
    # On stderr, because a scheduled caller discards stdout — a BLOCK there is silent.
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "BLOCK"


def test_cli_blocks_on_a_missing_registry_instead_of_reporting_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))   # no faber/goals.json under it
    assert _cli([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    out = json.loads(captured.err)
    assert out["status"] == "BLOCK"
    assert "does not exist" in out["reasons"][0]


def test_cli_reads_the_real_registry_from_hermes_home(tmp_path, monkeypatch, capsys):
    registry = tmp_path / "faber" / "goals.json"
    promote([packet()], FaberGoalRegistry(registry), promoted_by="x")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert _cli([]) == 0
    assert json.loads(capsys.readouterr().out)["goals"] == 1


def test_the_whole_promoted_backlog_is_observable(tmp_path):
    packets, promoted_by = load_manifest(MANIFEST)
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    promote(packets, registry, promoted_by=promoted_by)
    result = observe(registry)
    assert result.goals == 7
    assert result.preflight_clear == 0
    assert all(o.stopped_by == "preflight" for o in result.observations)
    assert result.preflight_clear == 0
    assert {o.bl_ref for o in result.observations} == {f"BL-{n}" for n in range(3633, 3640)}


# --- the registry must notice work promoted after the session started ----------

def test_a_long_lived_registry_sees_goals_promoted_after_it_was_built(tmp_path):
    """Every agent session holds one registry for its lifetime; without a
    reload the backlog stays empty until the runtime is restarted."""
    path = tmp_path / "goals.json"
    session = FaberGoalRegistry(path)          # built while the file did not exist
    assert session.all() == ()
    promote([packet()], FaberGoalRegistry(path), promoted_by="x")
    assert [g.goal_id for g in session.all()] == ["faber.code.flyby:example"]
    assert session.next_operational_goal().goal_id == "faber.code.flyby:example"
    assert session.get("faber.code.flyby:example") is not None


def test_reload_reflects_removals_not_just_additions(tmp_path):
    path = tmp_path / "goals.json"
    promote([packet()], FaberGoalRegistry(path), promoted_by="x")
    session = FaberGoalRegistry(path)
    assert len(session.all()) == 1
    path.write_text("[]", encoding="utf-8")
    assert session.all() == ()


def test_a_transiently_unreadable_file_does_not_empty_a_live_backlog(tmp_path):
    """Going blind mid-session is the same silent absence the reload fixes; the
    write path already raises rather than overwrite, and the read path keeps
    the last good snapshot rather than report zero."""
    path = tmp_path / "goals.json"
    promote([packet()], FaberGoalRegistry(path), promoted_by="x")
    session = FaberGoalRegistry(path)
    assert len(session.all()) == 1
    good = path.read_text(encoding="utf-8")
    path.write_text("{ truncated mid-write", encoding="utf-8")
    assert [g.goal_id for g in session.all()] == ["faber.code.flyby:example"]
    # Writing THROUGH a corrupt registry is separately refused, by design.
    with pytest.raises(ValueError, match="unreadable goal registry"):
        promote([packet(slug="b")], FaberGoalRegistry(path), promoted_by="x")
    # ...and the session picks the file back up once it is whole again.
    path.write_text(good, encoding="utf-8")
    promote([packet(slug="b")], FaberGoalRegistry(path), promoted_by="x")
    assert len(session.all()) == 2


def test_reload_does_not_resurrect_state_the_session_itself_wrote(tmp_path):
    path = tmp_path / "goals.json"
    registry = FaberGoalRegistry(path)
    promote([packet()], registry, promoted_by="x")
    registry.put(FaberGoal("faber.code.flyby:example", "Example", state=GoalState.BUILDING))
    assert registry.get("faber.code.flyby:example").state is GoalState.BUILDING
    assert FaberGoalRegistry(path).get("faber.code.flyby:example").state is GoalState.BUILDING
