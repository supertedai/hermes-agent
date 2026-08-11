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
    # BL-4029 L4: step 4 no longer judges CAD. A freshly promoted goal is held
    # by what step 4 CAN ask -- an unclaimed lease -- not by design evidence
    # the chain has not reached yet.
    assert any("lease" in r for r in obs.reasons)
    assert not any("CAD" in r for r in obs.reasons), \
        "preflight must not name CAD -- relocated to DesignGate (step 7)"


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
    # BL-4087: `observe` kaller ikke lenger `git_is_clean`, men `scope_is_clean`
    # -- repo-vid renhet var IKKE det `PreflightGate` spor om (kontraktens punkt
    # 2 sier «those leased files are clean»). Mocken paa `git_is_clean` ble
    # dermed VIRKNINGSLOES I STILLHET da produsenten ble rettet, og testen
    # feilet. Den feilet av riktig grunn: en mock som ikke lenger treffer noe,
    # er en test som maaler noe annet enn den tror.
    monkeypatch.setattr("agent.faber_observe.scope_is_clean",
                        lambda repo, scope: (True, (), 0))
    # BL-4029: leasen verifiseres naa mot AUTORITETEN, ikke mot evidensen. I en
    # enhetstest er autoriteten legitimt unaabar, saa den mockes -- men merk at
    # `"lease": "clear"` i evidensen under ALENE ikke lenger er nok.
    monkeypatch.setattr("agent.faber_observe.lease_clear_via_authority",
                        lambda paths: (True, "test: autoritet mocket"))
    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(
        FaberGoal(
            "faber.code.flyby:x", "X", cad_ref="CAD-M", adr_ref="ADR-1", bl_ref="BL-1",
            evidence={
                "gate": "morten", "owner_approval": "morten:2026-08-04",
                "cad_status": "verified", "adr_status": "accepted",
                "bl_status": "open", "obsidian_status": "fresh", "lease": "clear",
                # BL-4029: uten scope finnes ingen filer aa verifisere en lease PAA,
                # og da blokkerer gaten foer autoriteten i det hele tatt spoerres.
                "repo_scope": "hermes-agent: agent/code_workflow.py",
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
    joined = " ".join(obs.reasons)
    # BL-4029 L4: step 4 requires refs it can act on. "obsidian" is produced at
    # step 13, so demanding a reference to it here was the circularity.
    assert "git" in joined and "lease" in joined
    assert "obsidian" not in joined, \
        "step 4 must not require a Brain ref -- that is step 13's closeout"


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


def test_a_written_lease_claim_alone_no_longer_clears_preflight(tmp_path, monkeypatch):
    """BL-4029, instans 20 — og den var identisk med instans 1.

    Foerste versjon falt tilbake paa `evidence["lease"]` naar autoriteten ikke
    svarte. Hullet var at PRODUSENTEN kontrollerer om verifisering skjer: token-fila
    ligger paa `.15` og eies av `agent`, altsaa produsentens egen identitet. En
    `chmod 0644` -- eller `rm` -- ga tom token, uverifisert, og dermed at produsentens
    egen paastand ble aeret.

    Ironien: modus-sjekken er en HERDINGSKONTROLL, og den var den billigste bryteren
    for aa skru verifiseringen AV. En kontroll som feiler inn i aa stole paa den
    begrensede parten, er en kontroll den parten kan slaa av.
    """
    # BL-4087 (reviewer N1): ANDRE inerte mock, samme klasse som den over.
    # `observe` kaller ikke `git_is_clean` lenger, saa denne traff ingenting.
    # Testen passerte likevel, fordi `repo_paths` peker paa en ikke-git tmp_path
    # og `scope_is_clean` returnerer `(False, (), -1)` uansett — altsaa var
    # `preflight_clear == 0` ufalsifiserbar, og vakten overlevde kun paa den
    # andre assertionen. En mock som ikke treffer noe er en test som maaler noe
    # annet enn den tror.
    monkeypatch.setattr("agent.faber_observe.scope_is_clean",
                        lambda repo, scope: (True, (), 0))
    # Autoriteten svarer ikke -- akkurat scenariet produsenten kan fremtvinge.
    monkeypatch.setattr("agent.faber_observe.lease_clear_via_authority",
                        lambda paths: (None, "test: autoritet unaabar"))

    registry = FaberGoalRegistry(tmp_path / "goals.json")
    registry.put(
        FaberGoal(
            "faber.code.flyby:y", "Y", cad_ref="CAD-M", adr_ref="ADR-1", bl_ref="BL-1",
            evidence={
                "gate": "morten", "owner_approval": "morten:2026-08-04",
                "cad_status": "verified", "adr_status": "accepted",
                "bl_status": "open", "obsidian_status": "fresh",
                "lease": "clear",                      # <- produsentens paastand
                "repo_scope": "hermes-agent: agent/code_workflow.py",
                "git_ref": "abc1234", "lease_ref": "lease:hermes-agent",
                "obsidian_ref": "Brain/Symbiose Change Log.md",
            },
        )
    )
    result = observe(registry, repo_paths={"faber.code.flyby:y": str(tmp_path)})
    assert result.preflight_clear == 0, (
        "en SKREVET lease-paastand maa aldri klarere preflight naar autoriteten "
        "ikke har bekreftet den"
    )
    assert any("lease" in r.lower() for r in result.observations[0].reasons)


def test_empty_scope_cannot_have_a_verifiable_lease(tmp_path, monkeypatch):
    """Samme hull, stillere vei: tom sti-liste ga tidligere fallback til evidensen."""
    from agent.faber_observe import _resolve_lease_clear
    ok, note = _resolve_lease_clear({"repo_scope": "", "lease": "clear"})
    assert ok is False
    assert "ingen filer" in note


def test_the_git_ref_is_measured_before_it_is_taken_from_the_goal(tmp_path, monkeypatch):
    """BL-4087: `git` er en AUTORITATIV ref, saa den maales foerst.

    `evidence_for` leste den fra `goal.evidence["git_ref"]` -- et felt ingen
    produsent skriver, saa alle sju maalene BLOKKERTE paa «missing authoritative
    source refs: git» i HVER pakke sporet holder (495 av 495, maalt 2026-08-11;
    «340 ... samples» er BL-4029s
    arvede tall fra fem ANDRE filer, ikke maalt her).
    Nettopp fordi
    den er autoritativ kan den ikke komme fra maalet naar den kan maales: en sha
    et maal oppgir om seg selv er et sitat, ikke en maaling.
    """
    goal = FaberGoal("g", "G", cad_ref="C", adr_ref="A", bl_ref="B",
                     evidence={"git_ref": "fra-maalet"})
    maalt = evidence_for(goal, git_clean=True, git_ref="fra-maalingen")
    assert maalt.source_refs["git"] == "fra-maalingen"
    # ... og selvrapporten er noedloesningen, ikke foersteprioritet.
    umaalt = evidence_for(goal, git_clean=True, git_ref="")
    assert umaalt.source_refs["git"] == "fra-maalet"


def test_an_unreadable_tree_is_dirty_not_clean(tmp_path):
    """Ukjent er ikke rent -- og -1 sier at treet ikke lot seg lese."""
    from agent.faber_observe import scope_is_clean

    clean, inside, repo_dirty = scope_is_clean(str(tmp_path / "finnes-ikke"),
                                               "hermes-agent: a.py")
    assert clean is False and inside == () and repo_dirty == -1


def test_a_scope_that_names_no_files_is_unknown_not_clean(tmp_path):
    """Samme regel som LandingScopeGate: en ukjent mengde er ikke disjunkt fra noe."""
    import subprocess

    from agent.faber_observe import scope_is_clean

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    clean, inside, repo_dirty = scope_is_clean(str(tmp_path), "hermes-agent: ingen filer her")
    assert clean is False
    assert inside == ()
    assert repo_dirty >= 0, "treet var lesbart, saa tallet skal vaere maalt"


def test_dirt_outside_the_scope_does_not_block_but_is_recorded(tmp_path):
    """Kjernen i D-fiksen, og grensen for den.

    Skitt UTENFOR maalets scope blokkerer ikke -- ellers er gaten en vegg i et
    delt tre. Men den forsvinner ikke: `repo_dirty` teller den, og kalleren
    skriver tallet inn i observasjonen.
    """
    import subprocess

    from agent.faber_observe import scope_is_clean

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "min.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "andres.py").write_text("y = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "min.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)

    clean, inside, repo_dirty = scope_is_clean(str(tmp_path), "hermes-agent: min.py")
    assert clean is True, "andres.py er skitten, men den er ikke i MITT scope"
    assert inside == ()
    assert repo_dirty == 1, "og skitten er TELT, ikke skjult"

    (tmp_path / "min.py").write_text("x = 2\n", encoding="utf-8")
    clean, inside, _ = scope_is_clean(str(tmp_path), "hermes-agent: min.py")
    assert clean is False and inside == ("min.py",)
