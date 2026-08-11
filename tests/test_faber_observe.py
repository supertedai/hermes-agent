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


# ---------------------------------------------------------------------------
# G6 — REGISTERBROEN (BL-4095)
#
# Foer dette verifiserte INGEN gate en kontrakt-referanse mot noe register.
# `DesignGate` sjekket at strengen var ikke-tom, pluss en status PRODUSENTEN
# paastod. Maalt konsekvens: `ADR-DOES-NOT-EXIST-999` klarerte steg 7 noeyaktig
# som en ekte referanse. Det er kontrollen-som-ikke-kan-feile, i gaten som
# avgjoer om designgjennomgang har skjedd.
# ---------------------------------------------------------------------------

def _register(tmp_path, name, status_line):
    d = tmp_path / "docs"
    d.mkdir(exist_ok=True)
    (d / f"{name}.md").write_text(
        f"# {name} — test\n\n**Status:** `{status_line}`\n**Parent:** `MWP-UOSH-001`\n",
        encoding="utf-8")
    return str(d)


def test_a_reference_to_a_document_that_does_not_exist_is_MISSING(tmp_path):
    """Hullet alt annet hang paa, lukket."""
    from agent.faber_observe import resolve_contract_ref

    docs = _register(tmp_path, "ADR-HERMES-REAL-001", "ACCEPTED_ARCHITECTURE")
    status, note = resolve_contract_ref("ADR-DOES-NOT-EXIST-999", docs=docs)
    assert status == "missing", note
    assert "ADR-DOES-NOT-EXIST-999" in note


def test_a_real_accepted_document_resolves_and_carries_its_own_status_line(tmp_path):
    from agent.faber_observe import resolve_contract_ref

    docs = _register(tmp_path, "ADR-HERMES-REAL-001", "ACCEPTED_ARCHITECTURE / RUNTIME_GATED")
    status, note = resolve_contract_ref("ADR-HERMES-REAL-001", docs=docs)
    assert status == "accepted"
    # Evidensen er dokumentets EGEN linje, ikke vaar oppsummering av den.
    assert "ACCEPTED_ARCHITECTURE / RUNTIME_GATED" in note


def test_an_unaccepted_document_is_proposed_not_accepted(tmp_path):
    """Et dokument som FINNES er ikke det samme som en beslutning som er TATT."""
    from agent.faber_observe import resolve_contract_ref

    docs = _register(tmp_path, "ADR-HERMES-DRAFT-001", "PROPOSED / OWNER-REVIEW")
    assert resolve_contract_ref("ADR-HERMES-DRAFT-001", docs=docs)[0] == "proposed"


def test_a_superseded_document_is_rejected(tmp_path):
    from agent.faber_observe import resolve_contract_ref

    docs = _register(tmp_path, "ADR-HERMES-OLD-001", "SUPERSEDED BY ADR-HERMES-NEW-002")
    assert resolve_contract_ref("ADR-HERMES-OLD-001", docs=docs)[0] == "rejected"


def test_a_symbiose_number_is_UNVERIFIABLE_not_missing_and_not_accepted(tmp_path):
    """Den viktigste av de fire utfallene.

    `ADR-062` er et Symbiose-nummer; de registrene bor i `planning/` og vaulten
    paa `.13`, ikke naabart herfra. `accepted` ville paastaatt en verifisering vi
    ikke gjorde. `missing` ville anklaget et dokument som trolig finnes.
    UVERIFISERBAR er det sanne svaret -- og den passerer ikke `DesignGate`.
    """
    from agent.faber_observe import resolve_contract_ref

    docs = _register(tmp_path, "ADR-HERMES-REAL-001", "ACCEPTED_ARCHITECTURE")
    for ref in ("ADR-062", "BL-4087"):
        status, note = resolve_contract_ref(ref, docs=docs)
        assert status == "unverifiable", (ref, status, note)
        assert ".13" in note


def test_an_unreadable_register_is_unverifiable_not_empty(tmp_path):
    """Fravaer av svar er ikke et svar -- samme regel som `_porcelain`."""
    from agent.faber_observe import resolve_contract_ref

    status, note = resolve_contract_ref("ADR-HERMES-REAL-001",
                                        docs=str(tmp_path / "finnes-ikke"))
    assert status == "unverifiable"
    assert "lesbart" in note


def test_none_of_the_failure_states_pass_the_step_7_gate():
    """Vakten paa vakten: fail-closed maa vaere SANT, ikke bare ment.

    `DesignGate.ADR_OK`/`CAD_OK` er settene som slipper igjennom. Ingen av de
    fire ikke-aksepterte utfallene skal ligge i dem -- ellers har registerbroen
    lukket hullet i teorien og latt det staa i praksis.
    """
    from agent.code_workflow import DesignGate

    for bad in ("missing", "unverifiable", "proposed", "rejected", "unknown"):
        assert bad not in DesignGate.ADR_OK, bad
        assert bad not in DesignGate.CAD_OK, bad
    assert "accepted" in DesignGate.ADR_OK and "accepted" in DesignGate.CAD_OK


def test_the_producer_looks_the_ref_up_instead_of_taking_the_goals_word(monkeypatch):
    """Steg 7s inngangsdata SLAAS OPP, de tas ikke fra maalet.

    Maalet faar lyve saa mye det vil i `cad_status`/`adr_status`; testen bestaar
    bare hvis oppslaget vinner.
    """
    goal = FaberGoal("g", "G", cad_ref="CAD-HERMES-X-001", adr_ref="ADR-DOES-NOT-EXIST-999",
                     bl_ref="BL-1",
                     evidence={"cad_status": "verified", "adr_status": "accepted"})
    monkeypatch.setattr("agent.faber_observe.resolve_contract_ref",
                        lambda ref, docs=None: ("missing", f"{ref} finnes ikke"))
    ev = evidence_for(goal, git_clean=True, git_ref="abc")
    assert ev.adr_status == "missing", "maalets selvrapport vant over oppslaget"
    assert ev.cad_status == "missing"


def test_a_goal_without_a_ref_keeps_its_own_status(monkeypatch):
    """Uten referanse er det ingenting aa slaa opp -- da staar maalets felt.

    Ellers ville broen gjort et FRAVAER av referanse til en anklage om at
    dokumentet mangler, og de to er ulike funn.
    """
    goal = FaberGoal("g", "G", cad_ref="", adr_ref="", bl_ref="BL-1",
                     evidence={"cad_status": "verified", "adr_status": "accepted"})
    ev = evidence_for(goal, git_clean=True, git_ref="abc")
    assert ev.adr_status == "accepted"
    assert ev.cad_status == "verified"


# ---------------------------------------------------------------------------
# G6 runde 2 — reviewerens tre BLOCK, som regresjon
# ---------------------------------------------------------------------------

def test_BOTH_paths_gate_identically_on_a_fabricated_reference():
    """BLOCK 1: hullet var lukket i RAPPORTEN, ikke i GATEN.

    `faber_observe.evidence_for` er readback-stien. `faber_runtime.payload_for`
    er stien kjeden faktisk gater paa -- dicten blir `PreflightInput` og dommes
    av `DesignGate` inne i runneren. Foerste utkast lukket bare den foerste, saa
    `ADR-DOES-NOT-EXIST-999` klarerte steg 7 der kjeden KJOERER mens rapporten
    meldte BLOCK.
    """
    from agent import faber_runtime as fr
    from agent.code_workflow import DesignGate, PreflightInput

    goal = {"goal_id": "g", "title": "t", "cad_ref": "CAD-DOES-NOT-EXIST-999",
            "adr_ref": "ADR-DOES-NOT-EXIST-999", "bl_ref": "BL-1",
            "evidence": {"repo_scope": "hermes-agent: a.py", "cad_status": "verified",
                         "adr_status": "accepted", "bl_status": "open"}}
    obs = {"goal_id": "g", "git_ref": "abc", "reasons": [], "next_step": ""}

    pay = fr.payload_for(obs, goal, repo=".", build_root="/tmp/x", test_command=("t",))
    a = DesignGate().evaluate(PreflightInput(**pay["evidence"]))
    b = DesignGate().evaluate(evidence_for(
        FaberGoal("g", "t", cad_ref=goal["cad_ref"], adr_ref=goal["adr_ref"],
                  bl_ref="BL-1", evidence=goal["evidence"]),
        git_clean=True, git_ref="abc"))
    assert a.status is b.status, (a.reasons, b.reasons)
    assert a.status.value == "BLOCK", "den UTFOERENDE stien slapp den oppdiktede referansen"
    # PRESIST, ikke bare «begge blokkerer». Foerste utkast bestod selv naar
    # `adr_status` ble koblet av, fordi CAD alene felte gaten — testen maalte at
    # NOEN gate stengte, ikke at oppslaget skjedde. Proben viste det.
    assert pay["evidence"]["adr_status"] == "missing", pay["evidence"]
    assert pay["evidence"]["cad_status"] == "missing", pay["evidence"]


def test_a_partial_or_negated_status_is_not_accepted(tmp_path):
    """BLOCK 2: substring-matching snudde polariteten paa LEVENDE dokumenter.

    Reviewer maalte tre, og den foerste er en CAD -- altsaa paa den gatede
    stien: `Audit complete; open lanes recorded` ble `accepted`. Likeledes
    `PARTIAL / CANARY_COMPLETE_...`. Negasjonen bor som prefiks eller
    kvalifikator, ikke som eget ord, saa `_REJECTED_MARKERS`-sjekken foerst
    hjalp ikke.
    """
    from agent.faber_observe import resolve_contract_ref

    cases = {
        "Audit complete; open lanes recorded": "proposed",
        "PARTIAL / CANARY_COMPLETE_PRODUCER_WIRING_OPEN": "proposed",
        "INCOMPLETE / IN PROGRESS": "proposed",
        "NOT ACCEPTED": "proposed",
        "IKKE VEDTATT": "proposed",
        "PENDING ACCEPTANCE": "proposed",
        "ACCEPTED_ARCHITECTURE / RUNTIME_GATED": "accepted",
        "VEDTATT": "accepted",
        "SUPERSEDED BY ADR-X": "rejected",
    }
    for i, (status_line, want) in enumerate(cases.items()):
        name = f"ADR-HERMES-CASE{i:02d}-001"
        (tmp_path / f"{name}.md").write_text(
            f"# {name}\n\n**Status:** `{status_line}`\n", encoding="utf-8")
        got = resolve_contract_ref(name, docs=str(tmp_path))[0]
        assert got == want, f"{status_line!r} -> {got}, ventet {want}"


def test_the_base_document_owns_the_status_not_the_phase(tmp_path):
    """BLOCK 3: `hits[0]` lot FASE-fila vinne.

    `-` (0x2D) sorterer foer `.` (0x2E), saa `ADR-047-F5.md` slo `ADR-047.md`
    deterministisk -- og en fases aksept ble kreditert hele beslutningen.
    ADR-064/BL-4053: noeyaktig én fil erklaerer `adr_role: base` og eier statusen.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-047.md").write_text(
        "---\nadr_role: base\n---\n**Status:** `PROPOSED / not accepted`\n", encoding="utf-8")
    (tmp_path / "ADR-047-F5.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    status, note = resolve_contract_ref("ADR-047", docs=str(tmp_path))
    assert status == "proposed", note
    assert "ADR-047.md" in note and "F5" not in note

    # Motsatt polaritet: en supersedet FASE skal ikke felle en akseptert base.
    (tmp_path / "ADR-047.md").write_text(
        "---\nadr_role: base\n---\n**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    (tmp_path / "ADR-047-F5.md").write_text("**Status:** `SUPERSEDED`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-047", docs=str(tmp_path))[0] == "accepted"


def test_an_ambiguous_number_is_unverifiable_never_a_sort_order_choice(tmp_path):
    """Ingen base erklaert og flere filer: uavklart, ikke et valg."""
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-050-F1.md").write_text("**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    (tmp_path / "ADR-050-F2.md").write_text("**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    status, note = resolve_contract_ref("ADR-050", docs=str(tmp_path))
    assert status == "unverifiable"
    assert "adr_role: base" in note


def test_the_reference_lookup_is_case_insensitive(tmp_path):
    """`_REGISTER_REF` er IGNORECASE; globben maa vaere det ogsaa.

    Ellers gir `adr-hermes-x-001` `missing` for et dokument som FINNES — altsaa
    en anklage mot et ekte dokument, som er nettopp det `unverifiable` finnes
    for aa unngaa.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-HERMES-X-001.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    assert resolve_contract_ref("adr-hermes-x-001", docs=str(tmp_path))[0] == "accepted"


def test_the_real_register_resolves_without_a_false_accept():
    """Mot det EKTE registeret, ikke et syntetisk ett-fils-oppsett.

    Reviewer: hver G6-test bygde sin egen katalog, saa verken ekte statuslinjer
    eller fler-fil-tilfellet ble kjoert. Denne kjoerer mot registeret slik det
    faktisk staar, og krever at ingen ikke-akseptert linje leses som akseptert.
    """
    import os
    from pathlib import Path

    from agent.faber_observe import MWP_DOCS, resolve_contract_ref

    root = Path(os.environ.get("MWP_DOCS", MWP_DOCS))
    if not root.is_dir():
        pytest.skip("MWP-registeret er ikke naabart fra denne verten")
    refs = sorted({p.stem for p in root.glob("*.md")
                   if p.stem.split("-")[0] in {"ADR", "CAD", "BL"}})
    assert len(refs) > 20, f"registeret ser tomt ut: {len(refs)}"
    for ref in refs:
        status, note = resolve_contract_ref(ref)
        assert status in {"accepted", "proposed", "rejected", "unverifiable"}, (ref, status)
        if status == "accepted":
            line = note.split(":", 1)[-1].upper()
            for bad in ("PARTIAL", "IKKE", "NOT ", "PENDING", "INCOMPLETE", "OPEN"):
                assert bad not in line, f"{ref}: {status} paa en linje som sier {bad}: {note}"

    # BEGGE RETNINGER. Reviewer: denne asserterte bare «ingen falsk aksept»,
    # mens D1 var en falsk BLOCK -- saa den kunne per konstruksjon ikke fange
    # D1. Dette er den ene endringen som ville fanget D1 foer reviewer gjorde.
    import re as _re

    checked = 0

    for p in root.glob("*.md"):
        if p.stem.split("-")[0] not in {"ADR", "CAD", "BL"}:
            continue
        head = ""
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
            if raw.strip().lower().startswith("**status:**"):
                head = raw.split("**", 2)[-1].strip(" *:`").split("/")[0].strip().upper()
                break
        if not (head == "ACCEPTED" or head.startswith("ACCEPTED_")):
            continue
        # Kanonisk ref: filnavnet uten slug-halen. Et FILNAVN er ikke en referanse.
        m = _re.match(r"^((?:ADR|CAD|BL)-(?:[A-Z0-9][A-Z0-9.]*-)*?\d+)", p.stem, _re.IGNORECASE)
        if not m:
            continue
        checked += 1
        got = resolve_contract_ref(m.group(1))[0]
        assert got == "accepted", (
            f"{m.group(1)} har hodet {head!r} og skal resolvere accepted, fikk {got} "
            f"(fil: {p.name}) — dette er en FALSK BLOCK paa en ekte akseptert kontrakt")
    # Reviewer: `if not m: continue` er stille. Tell det som FAKTISK ble sjekket,
    # saa vakten ikke kan krympe til null uten aa si fra.
    # Maalt 2026-08-11: 21. Terskelen staar under det maalte med vilje, saa
    # ordinaer register-churn ikke gjoer vakten roed for noe annet enn en defekt
    # -- men den kan ikke krympe til null i stillhet.
    assert checked >= 15, f"begge-retninger-asserten sjekket bare {checked} dokumenter"


def test_a_negated_tail_vetoes_an_accepted_head(tmp_path):
    """Negasjons-vetoet, isolert.

    Mutasjonsproben viste at hode-regelen ALENE daekker alle statusene i
    testen over -- vetoet var dermed ubevist. Det som trenger det er en linje
    hvis HODE er akseptert og hvis HALE nekter. Uten denne testen kunne vetoet
    slettes uten at noe ble roedt.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-HERMES-VETO-001.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE / IKKE VEDTATT AV EIER`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-VETO-001", docs=str(tmp_path))[0] == "proposed"

    (tmp_path / "ADR-HERMES-VETO-002.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE / PARTIAL ROLLOUT`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-VETO-002", docs=str(tmp_path))[0] == "proposed"


def test_the_head_is_a_whole_word_not_a_substring(tmp_path):
    """Hode-regelen, isolert fra vetoet.

    Proben viste at en substring-mutant overlevde, fordi ingen test hadde en
    linje der de to reglene er UENIGE. Denne har det: hodet er `PROPOSED`, men
    et akseptert-ord staar lenger ute i linja uten aa vaere en negasjon.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-HERMES-SUB-001.md").write_text(
        "**Status:** `PROPOSED — supersedes ACCEPTED_ARCHITECTURE from ADR-X`\n",
        encoding="utf-8")
    status, note = resolve_contract_ref("ADR-HERMES-SUB-001", docs=str(tmp_path))
    assert status == "proposed", note


def test_the_exact_filename_wins_even_without_an_adr_role_marker(tmp_path):
    """Base-valget, isolert fra `adr_role`-regelen.

    Proben viste at `exact = []` overlevde, fordi base-fila i den forrige testen
    OGSAA erklaerte `adr_role: base` -- to verner daekket samme sak, saa aa fjerne
    det ene endret ingenting. Her er det bare filnavnet som kan redde det, og en
    fase som er akseptert mens basen ikke er.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-060.md").write_text(
        "**Status:** `PROPOSED / owner review`\n", encoding="utf-8")
    (tmp_path / "ADR-060-F2.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    status, note = resolve_contract_ref("ADR-060", docs=str(tmp_path))
    assert status == "proposed", note
    assert "ADR-060.md" in note and "F2" not in note


# ---------------------------------------------------------------------------
# Reviewer runde 3: KODEN var riktig, men tre fikser var holdt av INGENTING --
# inkludert D1 og D2 selv. Tre mutanter endret verdikten paa LEVENDE
# registerdata mens 620 tester og 74/74 mutanter meldte suksess.
#
# Mekanismen er verdt aa sitere, for den er fjerde forekomst av samme moenster:
# testen jeg skrev ETTER D1 staver negasjonene `IKKE VEDTATT` og
# `PARTIAL ROLLOUT` -- med MELLOMROM. D1 handlet om `IMPLEMENTED_NOT_LOADED`,
# altsaa UNDERSTREK. Vakten oevde paa skilletegnet defekten ikke var om.
# Testsettet flyttet seg til NABOLAGET av defekten og stoppet der.
# ---------------------------------------------------------------------------

def test_an_underscore_compound_is_one_token_not_a_negation(tmp_path):
    """D1s EGEN form, som regresjon.

    `ACCEPTED / IMPLEMENTED_NOT_LOADED / RESTART_GATE` er en LEVENDE akseptert
    ADR. `NOT` staar inne i et sammensatt token, og tokeniseringen splitter med
    vilje ikke paa `_`. Fjern `or ch == "_"` -- seks tegn -- og denne ADR-en blir
    falskt BLOKKERT.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-HERMES-UNDERSCORE-001.md").write_text(
        "**Status:** `ACCEPTED / IMPLEMENTED_NOT_LOADED / RESTART_GATE`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-UNDERSCORE-001", docs=str(tmp_path))[0] == "accepted"

    (tmp_path / "ADR-HERMES-UNBLOCKED-001.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE / UNBLOCKED`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-UNBLOCKED-001", docs=str(tmp_path))[0] == "accepted"


def test_a_truncated_reference_never_resolves_a_real_document():
    """D2, mot det EKTE registeret.

    `ADR-HERMES-CHAIN` og `CAD-MWP-DATA` navngir INTET dokument, men er prefiks
    til ett som finnes. Uten kravet om en avsluttende identifikator resolverte
    begge `accepted` -- en avkortet streng som klarerte steg 7.
    """
    import os
    from pathlib import Path

    from agent.faber_observe import MWP_DOCS, resolve_contract_ref

    if not Path(os.environ.get("MWP_DOCS", MWP_DOCS)).is_dir():
        pytest.skip("MWP-registeret er ikke naabart fra denne verten")
    for truncated in ("ADR-HERMES-CHAIN", "CAD-MWP-DATA", "ADR-J"):
        status, note = resolve_contract_ref(truncated)
        assert status != "accepted", f"{truncated} -> {status}: {note}"


def test_a_lone_phase_file_never_answers_for_the_decision(tmp_path):
    """Fase-sjekken paa ett-treffs-stien, som reviewer viste var uholdt.

    `ADR-047` med BARE `ADR-047-F5.md` i katalogen: snarveien `len(hits) == 1`
    ville gitt fasens aksept til hele beslutningen (ADR-064/BL-4053).
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-047-F5.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    status, note = resolve_contract_ref("ADR-047", docs=str(tmp_path))
    assert status == "unverifiable", note


def test_a_truncation_is_reported_as_a_truncation_not_as_an_ambiguous_base(tmp_path):
    """En gate som forklarer seg feil er klassen denne BL-en jakter paa."""
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-HERMES-LONGNAME-001.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE`\n", encoding="utf-8")
    status, note = resolve_contract_ref("ADR-HERMES-LONGNAME-0", docs=str(tmp_path))
    assert status in {"missing", "unverifiable"}
    assert "adr_role" not in note, note


def test_a_delimiter_without_spaces_still_splits_the_head(tmp_path):
    """Hode-splittingen, som reviewer viste var holdt av INGENTING.

    `head = line.strip(...)` overlevde hele suiten inkludert
    begge-retninger-asserten, fordi ingen LEVENDE statuslinje bruker en
    delimiter uten mellomrom rundt. Feilmoden er D1s egen klasse: en framtidig
    `ACCEPTED_ARCHITECTURE/RUNTIME_GATED` uten mellomrom ville blitt en FALSK
    BLOCK paa en ekte akseptert kontrakt.
    """
    from agent.faber_observe import resolve_contract_ref

    (tmp_path / "ADR-HERMES-TIGHT-001.md").write_text(
        "**Status:** `ACCEPTED_ARCHITECTURE/RUNTIME_GATED`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-TIGHT-001", docs=str(tmp_path))[0] == "accepted"

    (tmp_path / "ADR-HERMES-TIGHT-002.md").write_text(
        "**Status:** `SUPERSEDED;BY ADR-X`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-TIGHT-002", docs=str(tmp_path))[0] == "rejected"

    # Reviewer runde 5: `_status_word` splitter paa TRE delimitere, og testen
    # daekket to. Aa fjerne `.split(",")[0]` overlevde hele suiten. Et navn som
    # paastaar en generell regel mens det maaler to tredeler av den, er samme
    # klasse som D-B -- paa samme linje.
    (tmp_path / "ADR-HERMES-TIGHT-003.md").write_text(
        "**Status:** `SUPERSEDED,BY ADR-X`\n", encoding="utf-8")
    assert resolve_contract_ref("ADR-HERMES-TIGHT-003", docs=str(tmp_path))[0] == "rejected"


def test_the_non_english_accepted_vocabulary_is_held(tmp_path):
    """`_ACCEPTED_OTHER` var holdt av ETT medlem.

    `VERIFIED` og `FRESH` er levende vokabular i `DesignGate.CAD_OK`, saa et
    stille tap der er en D1-klasse falsk BLOCK -- selv om ingen dokument bruker
    dem i dag.
    """
    from agent.faber_observe import resolve_contract_ref

    for i, word in enumerate(("VEDTATT", "UTFOERT", "UTFØRT", "VERIFIED", "FRESH")):
        name = f"ADR-HERMES-VOCAB{i}-001"
        (tmp_path / f"{name}.md").write_text(
            f"**Status:** `{word}`\n", encoding="utf-8")
        assert resolve_contract_ref(name, docs=str(tmp_path))[0] == "accepted", word
