"""Kjøres SØMMENE, eller er de bare nåbare? (BL-4070)

`tests/test_chain_is_wired.py` spør ett spørsmål per komponent: *finnes det en
importsti fra kjeden til deg?* Den er ærlig om at det er det svakeste kravet som
ikke kan oppfylles ved et uhell — men den sier det selv:

    En import er ikke et kall.

Denne fila er kallet. For hver av de fire sømmene BL-4070 lukket driver den
kjedens egen inngang og måler at utføreren FAKTISK ble spurt — og, viktigere, at
svaret som brukes nedstrøms er det MÅLTE, ikke det avsenderen skrev.

Feilklassen begge filene finnes for er den samme: en komponent som er til stede
og ser koblet ut. Ratsjetten i den andre fila ville gått til 0 av en `import`
lagt inn kun for å tilfredsstille den. Det er nettopp derfor denne fila må
finnes, og hvorfor den ikke skal slås sammen med den: de svarer på to spørsmål
som kan ha ulike svar.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent import faber_runtime as fr  # noqa: E402
from agent.code_workflow import (  # noqa: E402
    GovernedRunResult,
    LandingEvidence,
    PreflightInput,
    ReviewVerdict,
)
from agent.lease_authority import LeaseOutcome  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_operator_state(tmp_path, monkeypatch):
    """Reviewer 5: testene skrev inn i LEVENDE operatoer-tilstand.

    `skill_selector.default_trace_path()` er `~/.hermes/skill-selection-trace.jsonl`
    naar `HERMES_HOME` er usatt, og sporet er nettopp hvordan man ville MAALT hvor
    ofte kjeden velger skills. Testrader forurenser den maalingen — en test som
    skriver inn i tallet den maaler, er samme feilklasse som resten av denne fila.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _evidence(**over) -> PreflightInput:
    base = dict(
        git_clean=True,
        lease_clear=False,
        cad_status="accepted",
        adr_status="accepted",
        bl_status="open",
        obsidian_status="fresh",
        source_refs={"lease": "declared/by/payload.py"},
    )
    base.update(over)
    return PreflightInput(**base)


def _landing(commit: str = "cafe1234", files=("a.py",)) -> LandingEvidence:
    return LandingEvidence(
        commit=commit,
        reviewer=ReviewVerdict.PASS,
        tests="tests: 1 passed",
        readback="readback ok",
        runtime_smoke="smoke ok",
        rollback="revert cafe1234",
        brain_change_log="change log ok",
        selfstate="selfstate ok",
        commit_closer="closer ok",
        landing_set=tuple(files),
    )


# ---------------------------------------------------------------------------
# STEG 6 — lease_take
# ---------------------------------------------------------------------------

def test_no_lease_spec_leaves_evidence_untouched():
    """Uten `lease` i payloaden skal steg 6 ikke røre noe.

    Replay- og testriggene sender ikke `lease`. Om steg 6 hadde nullstilt
    lease-settet der, ville innkoblingen brutt hver eksisterende kaller — og
    fristelsen hadde vært å slå den av igjen.
    """
    ev = _evidence()
    assert fr.lease_take({}, ev) is ev


def test_authority_answer_replaces_the_payloads_lease_set(monkeypatch):
    """Det er AUTORITETENS `acquired` som blir kjedens lease-sett.

    Halvdelen som er lett å glemme. Tar man leasen uten å bytte kilde, dømmer
    steg 11 fortsatt landingssettet mot en streng produsenten skrev — og da
    beviser hverken steg 4 eller steg 11 noe. Testen ber om ÉN sti og lar
    autoriteten svare med en ANNEN, slik at bare det målte kan bestå.
    """
    monkeypatch.setattr(
        "agent.lease_authority.claim",
        lambda paths, ttl=0, note="": LeaseOutcome(
            ok=True, acquired=("granted/by/authority.py",), reason="lease tatt"),
    )
    out = fr.lease_take({"lease": {"paths": ["asked/for.py"]}}, _evidence())
    assert out.source_refs["lease"] == "granted/by/authority.py"
    assert "asked/for.py" not in out.source_refs["lease"]
    assert out.lease_clear is True


def test_failed_claim_clears_the_lease_set_and_the_flag(monkeypatch):
    """En mislykket lease er ikke en lease. Begge nedstrømsgrenser må lukke."""
    monkeypatch.setattr(
        "agent.lease_authority.claim",
        lambda paths, ttl=0, note="": LeaseOutcome(
            ok=False, acquired=(), reason="autoriteten unåbar"),
    )
    out = fr.lease_take({"lease": {"paths": ["x.py"]}}, _evidence())
    assert out.lease_clear is False
    assert out.source_refs["lease"] == ""
    assert "unåbar" in out.source_refs["lease_authority"]


def test_failed_claim_makes_step_8_unreachable(monkeypatch):
    """Fail-closed hele veien: uten lease kan steg 8 ikke bygge.

    Dette er selve grunnen til at feltet nullstilles i stedet for å beholde
    payloadens verdi. `build_callable` nekter på et tomt lease-sett, så en
    mislykket lease kan ikke bli til en tick som skriver filer.
    """
    from agent.code_workflow import GovernedCodeRunner

    monkeypatch.setattr(
        "agent.lease_authority.claim",
        lambda paths, ttl=0, note="": LeaseOutcome(ok=False, acquired=(), reason="nektet"),
    )
    ev = fr.lease_take({"lease": {"paths": ["x.py"]}}, _evidence())
    payload = {"implement": {"repo_root": "/tmp", "goal_id": "g"}}
    with pytest.raises(ValueError, match="names no files"):
        fr.build_callable(payload, GovernedCodeRunner(), ev)


def test_lease_scope_string_is_parsed_not_rejected(monkeypatch):
    """`paths` godtar broens fritekst-scope, ikke bare en liste."""
    seen: dict[str, tuple[str, ...]] = {}

    def _claim(paths, ttl=0, note=""):
        seen["paths"] = tuple(paths)
        return LeaseOutcome(ok=True, acquired=tuple(paths), reason="ok")

    monkeypatch.setattr("agent.lease_authority.claim", _claim)
    fr.lease_take({"lease": {"paths": "hermes-agent: a/b.py, c/d.py"}}, _evidence())
    assert seen["paths"] == ("a/b.py", "c/d.py")


# ---------------------------------------------------------------------------
# STEG 11 — landing_callable
# ---------------------------------------------------------------------------

def test_without_land_spec_the_literal_branch_is_used():
    literal = _landing("literal01")
    got = fr.landing_callable({}, None, literal)({})
    assert got is literal


def test_real_landing_requires_the_judged_prelanding_set():
    """Uten `prelanding` finnes ikke settet vakten dømte.

    BL-4051: med to innganger for settet landet en uleaset fil, og målet gikk
    til LANDED. Derfor kan settet ikke oppgis i payloaden — det MÅ komme fra
    evidensen `LandingScopeGate` målte mot leasen.
    """
    with pytest.raises(ValueError, match="requires 'prelanding'"):
        fr.landing_callable({"land": {"message": "BL-x: noe"}}, None, _landing())


def test_real_landing_requires_a_message():
    with pytest.raises(ValueError, match="land.message"):
        fr.landing_callable({"land": {"message": "  "}}, _landing(), _landing())


def test_the_hand_is_called_with_the_judged_set_and_the_measured_answer_wins(monkeypatch):
    """Hånden får det DØMTE settet; nedstrøms brukes det MÅLTE svaret.

    Prelanding deklarerer `a.py`; git leser tilbake `a.py` under en annen sha.
    Består testen bare hvis den målte shaen — ikke den deklarerte — er det som
    kommer ut, og hvis observasjonen ble fylt.
    """
    calls: dict[str, object] = {}

    class _FakeExecutor:
        def land(self, landing_set, message):
            calls["set"] = tuple(landing_set)
            calls["message"] = message

            class _R:
                ok = True
                commit = "measured99"
                committed = ("a.py",)
                reasons = ()
            return _R()

    monkeypatch.setattr("agent.faber_landing.GitLandingExecutor",
                        lambda *a, **k: _FakeExecutor())
    observed = fr.LandingObservation()
    pre = _landing("declared00", files=("a.py",))
    hand = fr.landing_callable({"land": {"message": "BL-4070: sy sammen"}}, pre,
                               _landing(), observed=observed)
    out = hand({})
    assert calls["set"] == ("a.py",)
    assert calls["message"] == "BL-4070: sy sammen"
    assert out.commit == "measured99"
    assert observed.evidence is not None
    assert observed.evidence.commit == "measured99"


def test_a_refused_landing_raises_rather_than_reporting_success(monkeypatch):
    """Nekter hånden, kommer vi ikke til LANDED. Runneren blokkerer målet."""
    from agent.faber_landing import LandingRefused

    class _FakeExecutor:
        def land(self, landing_set, message):
            class _R:
                ok = False
                commit = ""
                committed = ()
                reasons = ("fremmede filer staget",)
            return _R()

    monkeypatch.setattr("agent.faber_landing.GitLandingExecutor",
                        lambda *a, **k: _FakeExecutor())
    observed = fr.LandingObservation()
    hand = fr.landing_callable({"land": {"message": "m"}}, _landing(), _landing(),
                               observed=observed)
    with pytest.raises(LandingRefused):
        hand({})
    assert observed.evidence is None


def test_the_literal_branch_never_fills_the_observation():
    """En literal er ikke en måling, og skal ikke kunne bli en.

    Uten dette ville steg 12/13 lest en commit tilbake mot payloadens eget
    filsett — avsenderen sammenlignet med seg selv.
    """
    observed = fr.LandingObservation()
    fr.landing_callable({}, None, _landing(), observed=observed)({})
    assert observed.evidence is None


# ---------------------------------------------------------------------------
# STEG 12/13 — postcommit_callable
# ---------------------------------------------------------------------------

def test_no_postcommit_spec_gives_no_callable():
    assert fr.postcommit_callable({}, fr.LandingObservation()) is None


#: Minimalt gyldig steg-12/13-spec. Hvert felt er PAAKREVD av en grunn reviewer
#: maalte: uten `test_paths` kjoerer pytest over kildefiler og samler ingenting;
#: uten noeyaktig ett av `container`/`no_runtime_target` slipper steg 12 igjennom
#: uten aa maale en prosess (BL-4052 reviewer B1).
_PC_SPEC = {
    "test_paths": ["tests/test_chain_seam_wiring.py"],
    "no_runtime_target": "ren biblioteksendring, ingen prosess betjener den",
}


def _landed_goal(state=None):
    from agent.code_workflow import FaberGoal, GoalState

    return FaberGoal("g", "t", state=state or GoalState.LANDED)


def _fake_adapters(monkeypatch, *, apply=True, **over):
    """Erstatt de sju adapterne — MED DE EKTE SIGNATURENE.

    Reviewer BLOCK 1: foerste versjon fakte `runtime_smoke_step` som
    ``lambda c, modules=(), repo=None``. Den ekte funksjonen har ingen
    ``modules``-parameter, saa produksjonsstien kastet TypeError paa hver tick
    mens testen var groenn. En fake med en signatur originalen ikke kan ha,
    beviser ingenting om originalen. `test_every_faked_adapter_matches_the_real_signature`
    under gjoer den feilen umulig aa gjenta i stillhet.
    """
    defaults = {
        "run_tests": lambda paths, *, repo=None: "tests: 1 passed",
        "commit_closer": lambda sha, *, repo=None: "closer ok",
        "brain_change_log": lambda sha, *, repo=None, path=None: "change log ok",
        "selfstate": lambda sha, *, repo=None: "selfstate ok",
        "rollback": lambda sha, *, repo=None: "revert ok",
        "postcommit_readback": (
            lambda sha, *, expected_files, require_ref="", repo=None: "readback ok"),
        "runtime_smoke_step": (
            lambda sha, *, repo=None, container="", host_path="", repo_relpath="",
            no_runtime_target="", docker_cmd=None, check_local_fleet=True: "smoke ok"),
    }
    defaults.update(over)
    if not apply:
        return defaults
    for name, fn in defaults.items():
        monkeypatch.setattr(f"agent.faber_postcommit_adapters.{name}", fn)
    return defaults


def test_every_faked_adapter_matches_the_real_signature(monkeypatch):
    """Vakten mot BLOCK 1: en fake maa kunne kalles slik originalen kalles.

    Dette er ikke pedanteri. Den ene mismatchen som slapp igjennom gjorde at
    steg 12 kastet TypeError paa hver eneste ekte tick, `PostcommitLoop`s ytre
    `except` slukte den, og hele testsuiten var groenn.

    OG DENNE VAKTEN VAR SELV VAKUOES I FOERSTE UTKAST (reviewer runde 2, BLOCK 2).
    `_fake_adapters` APPLISERTE monkeypatchene foer den returnerte, saa
    `getattr(pca, name)` leste tilbake FAKEN. Testen sammenlignet hver fake med
    seg selv. Reviewer beviste det ved aa sette den opprinnelige BLOCK 1-faken
    (`lambda sha, modules=(), repo=None`) tilbake: `1 passed`. Vakten skrevet for
    aa gjoere BLOCK 1 umulig aa gjenta i stillhet, kunne ikke oppdage BLOCK 1.
    Signaturene fanges derfor NAA foer noe patches — `apply=False`.
    """
    import inspect

    from agent import faber_postcommit_adapters as pca

    fakes = _fake_adapters(monkeypatch, apply=False)
    # OG DETTE ER DET SOM GJOER VAKTEN EKTE. Mutasjonsproben viste det: setter
    # man `apply=False` tilbake til default, blir testen GROENN — fordi en fake
    # sammenlignet med seg selv passerer i begge retninger. Assertionen under er
    # hele forskjellen mellom en maaling og en tautologi.
    for name in fakes:
        real = getattr(pca, name)
        # `is not fake` var IKKE nok (reviewer runde 3, som beviste det):
        # `_fake_adapters` lager ferske lambdaer hver gang, saa en fake fra en
        # ANNEN patcher er trivielt `is not` denne. Identitet er feil spoersmaal;
        # OPPHAV er riktig. En lambda heter `<lambda>` og kan ikke passere.
        assert getattr(real, "__module__", "") == pca.__name__, (
            f"{name}: modulattributtet kommer fra {getattr(real, '__module__', '?')}, "
            "ikke fra adaptermodulen — noe patchet pca foer signaturene ble fanget")
        assert getattr(real, "__name__", "") == name, (
            f"{name}: modulattributtet heter {getattr(real, '__name__', '?')} — "
            "signaturene maa fanges FOER noe patches, ellers sammenligner testen "
            "faken med seg selv")
    real_sigs = {name: inspect.signature(getattr(pca, name)) for name in fakes}
    for name, fake in fakes.items():
        real_params = real_sigs[name].parameters
        fake_params = inspect.signature(fake).parameters
        for pname, p in fake_params.items():
            assert pname in real_params, f"{name}: faken har '{pname}', originalen har det ikke"
            assert p.kind is real_params[pname].kind, (
                f"{name}: '{pname}' er {p.kind} i faken og "
                f"{real_params[pname].kind} i originalen — kallformen kan divergere")
        # Begge retninger: en fake som MANGLER et paakrevd argument er like
        # ubrukelig som en som finner paa et.
        for pname, p in real_params.items():
            if p.default is inspect.Parameter.empty and p.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY):
                assert pname in fake_params, (
                    f"{name}: originalen krever '{pname}', faken tar det ikke imot")


def test_the_selector_spy_matches_the_real_select_for_task(monkeypatch):
    """Samme regel som for postcommit-adapterne, anvendt paa selektor-spionen."""
    import inspect

    from agent import skill_selector

    real = inspect.signature(skill_selector.select_for_task).parameters

    def _spy(task_text, *, stage="unspecified", limit=3, index_path=None, trace_path=None):
        return None

    for pname, p in inspect.signature(_spy).parameters.items():
        assert pname in real, f"spionen har '{pname}', originalen har det ikke"
        assert p.kind is real[pname].kind, f"'{pname}' har ulik parametertype"


def test_postcommit_requires_a_test_target(monkeypatch):
    """BLOCK 4: uten `test_paths` kan steg 12/13 ikke bestaa, ved konstruksjon."""
    with pytest.raises(ValueError, match="test_paths"):
        fr.postcommit_callable({"postcommit": {"no_runtime_target": "x"}},
                               fr.LandingObservation())


def test_postcommit_requires_exactly_one_runtime_answer():
    """BLOCK 1, andre halvdel: verken stillhet eller begge deler er et svar."""
    with pytest.raises(ValueError, match="exactly one"):
        fr.postcommit_callable({"postcommit": {"test_paths": ["t.py"]}},
                               fr.LandingObservation())
    with pytest.raises(ValueError, match="exactly one"):
        fr.postcommit_callable(
            {"postcommit": {"test_paths": ["t.py"], "container": "c",
                            "no_runtime_target": "r"}},
            fr.LandingObservation())


def test_postcommit_refuses_when_no_hand_measured_a_landing():
    """Tom observasjon → BLOCK, ikke tilbakefall til det deklarerte settet."""
    run = fr.postcommit_callable({"postcommit": _PC_SPEC}, fr.LandingObservation())
    result = run(GovernedRunResult(goal=_landed_goal()))
    assert result.success is False
    assert result.missing == ("landing",)
    assert "MAALT" in result.error


def test_postcommit_refuses_on_a_goal_that_never_landed():
    """Reviewer 4: entailmenten LANDED ⇒ reviewer-PASS maa staa paa egne bein her."""
    from agent.code_workflow import GoalState

    observed = fr.LandingObservation()
    observed.evidence = _landing("m1", files=("a.py",))
    run = fr.postcommit_callable({"postcommit": _PC_SPEC}, observed)
    result = run(GovernedRunResult(goal=_landed_goal(GoalState.BUILDING)))
    assert result.success is False
    assert result.missing == ("state",)


def test_postcommit_reads_back_against_the_measured_set_not_the_payloads(monkeypatch):
    """Steg 13 sammenligner commiten mot det GIT leste tilbake.

    Payloaden får lov til å oppgi et helt annet filsett; testen består bare hvis
    tilbakelesingen ignorerer det og bruker observasjonen.
    """
    seen: dict[str, object] = {}

    def _readback(sha, *, expected_files, require_ref="", repo=None):
        seen["sha"] = sha
        seen["expected"] = tuple(expected_files)
        return "readback ok"

    _fake_adapters(monkeypatch, postcommit_readback=_readback)

    observed = fr.LandingObservation()
    observed.evidence = _landing("measured99", files=("really/landed.py",))
    run = fr.postcommit_callable(
        {"postcommit": {**_PC_SPEC, "expected_files": ["payload/said.py"]}}, observed)
    result = run(GovernedRunResult(goal=_landed_goal()))
    assert seen["sha"] == "measured99"
    assert seen["expected"] == ("really/landed.py",)
    assert result.success is True
    # De fire bevis-stegene kan aldri replayes; alle sju kjørte her.
    assert "readback" in result.executed and "runtime_smoke" in result.executed


def test_postcommit_runs_against_the_real_smoke_step_and_is_refused_honestly(monkeypatch):
    """Steg 12 drives mot den EKTE `runtime_smoke_step`, ikke mot en fake.

    Reviewer krevde dette eksplisitt, og det er den eneste maaten aa vise at
    kallformen stemmer. Den lokale flaaten er tom paa `.15` (ADR-043), og
    erklaeringen om manglende kjoeretidsmaal er ekte — saa det som avgjoer er
    import-sjekken paa en oppdiktet sha, som skal BLOKKERE med en begrunnelse.
    """
    from agent import faber_postcommit_adapters as pca

    _fake_adapters(monkeypatch, runtime_smoke_step=pca.runtime_smoke_step)
    observed = fr.LandingObservation()
    observed.evidence = _landing("0" * 40, files=("agent/faber_runtime.py",))
    result = fr.postcommit_callable({"postcommit": _PC_SPEC}, observed)(
        GovernedRunResult(goal=_landed_goal()))
    # Ingen TypeError: kallformen stemmer. Resultatet er et REELT avslag.
    assert "unexpected keyword" not in result.error
    assert result.success is False


def test_postcommit_propagates_a_reasoned_refusal(monkeypatch):
    """En StepBlocked skal bære GRUNNEN videre, ikke bli til «tom evidens»."""
    from agent.faber_postcommit_adapters import StepBlocked

    def _boom(sha, *, expected_files, require_ref="", repo=None):
        raise StepBlocked("readback", "fremmed fil i commiten")

    _fake_adapters(monkeypatch, postcommit_readback=_boom)
    observed = fr.LandingObservation()
    observed.evidence = _landing("m1", files=("a.py",))
    result = fr.postcommit_callable({"postcommit": _PC_SPEC}, observed)(
        GovernedRunResult(goal=_landed_goal()))
    assert result.success is False
    assert "fremmed fil" in result.error


# ---------------------------------------------------------------------------
# BROEN — steg 6 lest, og skill-valget
# ---------------------------------------------------------------------------

def test_bridge_keeps_unverified_distinct_from_not_clear(monkeypatch):
    """UVERIFISERT er en tredje verdi, ikke en pen måte å si «ikke ren» på."""
    from agent import faber_control_bridge as bridge

    monkeypatch.setattr("agent.lease_authority.check",
                        lambda paths: (None, "autoriteten unåbar — UVERIFISERT"))
    state = bridge.lease_state_for("hermes-agent: a/b.py")
    assert state["clear"] is None
    assert state["paths"] == ["a/b.py"]

    monkeypatch.setattr("agent.lease_authority.check",
                        lambda paths: (False, "1 hos andre"))
    assert bridge.lease_state_for("hermes-agent: a/b.py")["clear"] is False


def test_bridge_asks_nothing_when_the_scope_names_no_files(monkeypatch):
    from agent import faber_control_bridge as bridge

    def _never(paths):  # pragma: no cover - skal ikke kalles
        raise AssertionError("autoriteten ble spurt uten stier")

    monkeypatch.setattr("agent.lease_authority.check", _never)
    state = bridge.lease_state_for("")
    assert state["clear"] is None and state["paths"] == []


def _write_catalog(home, *, skills):
    """Minimal, GYLDIG skills-katalog i det isolerte `HERMES_HOME`.

    Uten denne er katalogen fraværende, `select_for_task` degraderer til
    `coverage="unknown", considered=0, selected=[]` — og enhver assertion som
    godtar «unknown» godtar dermed at seleksjonen ALDRI KJØRTE.
    """
    import json as _json
    from datetime import datetime, timezone

    # `generated_at` MAA vaere NAA, ikke en dato skrevet inn i kildekoden.
    # Reviewer runde 5: en hardkodet dato er groenn i dag og ville fra i morgen
    # STILLE flyttet testen over i `partial`-grenen for alltid — den ville
    # fortsatt passere, men ikke lenger maale det den ble skrevet for. Det er
    # samme raatning som `3876156f1` («to datobundne paastander raatnet paa en
    # halvtime»), i en test hvis hele formaal er aa hindre stille utgliding.
    home.mkdir(parents=True, exist_ok=True)
    (home / "skills-catalog.json").write_text(_json.dumps({
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_coverage": "complete",
        "catalog_coverage_complete": True,
        "roots_missing": [],
        "skill_count": len(skills),
        "skills": skills,
    }), encoding="utf-8")


def test_bridge_selects_skills_for_a_goal_with_text(tmp_path, monkeypatch):
    """Seleksjonen KJØRER — målt mot en katalog med kjent innhold.

    REVIEWER RUNDE 4 FELTE FORRIGE VERSJON, OG DET ER DEN SKARPESTE RETTELSEN I
    HELE BL-EN. De slettet selve kallet i broen og lot importen stå::

        return {"queryable": True, "coverage": "UNKNOWN", "selected": []}

    53 tester passerte, og ratsjetten skrev fortsatt `[koblet ] skill_selector`.
    Sømmen denne BL-en finnes for å koble kunne altså fjernes uten at én eneste
    test merket det.

    To ting kompenserte hverandre til vakuum: den isolerte `HERMES_HOME` hadde
    ingen katalog, så `select_for_task` degraderte til `coverage="unknown"` — og
    assertionen godtok «unknown». Men «unknown» er nettopp verdien som betyr AT
    SELEKSJONEN IKKE KJØRTE. Fila mi har «En import er ikke et kall. Denne fila
    er kallet» i sin egen header, og gjorde så unntak for én søm.
    """
    from agent import faber_control_bridge as bridge

    home = tmp_path / "hermes-home"
    _write_catalog(home, skills=[
        {"name": "faber-landing", "description": "land a governed commit through the executor",
         "body": "landing executor commit staging readback", "tags": ["faber"], "aliases": []},
        {"name": "victron-energy", "description": "battery state of charge and solar",
         "body": "battery solar grid tibber", "tags": ["iot"], "aliases": []},
    ])
    monkeypatch.setenv("HERMES_HOME", str(home))

    got = bridge.skill_selection_for(
        {"title": "wire the faber landing executor", "repo_scope": "hermes-agent: agent/x.py"})

    # «unknown» er IKKE i det aksepterte settet: den betyr at seleksjonen ikke kjørte.
    assert got["coverage"].lower() in {"complete", "partial", "missing"}, got
    assert got["considered"] > 0, "katalogen ble aldri lest — ingenting ble vurdert"
    assert [s["name"] for s in got["selected"]][:1] == ["faber-landing"], got


def test_bridge_hands_the_selector_the_goals_text_and_the_right_stage(monkeypatch):
    """Den andre halvdelen: er det BROEN som spør, eller returnerer den en literal?

    Reviewer-mutanten erstattet kallet med et ordrett dict. Denne testen spionerer
    på selektoren, så et slikt bytte gir null kall og feiler umiddelbart — uansett
    hva returverdien ser ut som.
    """
    from agent import faber_control_bridge as bridge
    from agent import skill_selector

    seen: dict[str, object] = {}

    class _Sel:
        def to_json(self):
            return {"coverage": "complete", "considered": 1, "selected": [],
                    "queryable": True, "sentinel": "fra-selektoren"}

    # Parameternavnet er `task_text`, som i originalen. Reviewer runde 5:
    # signaturvakten daekker bare `faber_postcommit_adapters`, saa denne faken
    # var ikke maalt — og dens egen begrunnelse («en fake maa kunne kalles slik
    # originalen kalles») gjelder like fullt her.
    def _spy(task_text, *, stage="unspecified", limit=3, index_path=None, trace_path=None):
        seen["text"] = task_text
        seen["stage"] = stage
        return _Sel()

    monkeypatch.setattr(skill_selector, "select_for_task", _spy)
    got = bridge.skill_selection_for({"title": "land the executor",
                                      "description": "steg 11",
                                      "repo_scope": "hermes-agent: agent/x.py"})
    assert seen["stage"] == "bridge:cross"
    for fragment in ("land the executor", "steg 11", "agent/x.py"):
        assert fragment in str(seen["text"]), seen
    # Returverdien MÅ være selektorens egen, ikke en bro-lokal literal.
    assert got.get("sentinel") == "fra-selektoren", got


def test_bridge_never_claims_absence_for_a_textless_goal():
    """Ingen tekst → ikke spørbar. Det er ikke det samme som «ingen skills passer»."""
    from agent import faber_control_bridge as bridge

    got = bridge.skill_selection_for({})
    assert got["queryable"] is False
    assert got["coverage"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# NÆRVÆR, IKKE SANNHETSVERDI
#
# Første utkast brukte `if not spec`. Da ble `{"postcommit": {}}` — som leses av
# ethvert menneske som «kjør steg 12/13 med standardvalg» — STILLE til «hopp
# over tilbakelesingen». Et steg som forsvinner fordi konfigurasjonen var tom
# er den samme stille utelatelsen kjeden er bygget for å hindre; her fant min
# egen test den. Disse tre pinner formen, ikke bare fiksen.
# ---------------------------------------------------------------------------

def test_empty_postcommit_object_is_an_error_not_a_silent_skip():
    """Naervaerende men tom spec skal KASTE, aldri hoppe stille over steg 12/13.

    Foerste utkast returnerte `None` her. Reviewer viste at defaultene bak den
    ikke kunne bestaa uansett, saa "kjoer med standardvalg" var en umulighet
    forkledd som en mulighet. Naa sier feilmeldingen hva som mangler.
    """
    with pytest.raises(ValueError):
        fr.postcommit_callable({"postcommit": {}}, fr.LandingObservation())


def test_empty_land_object_is_an_error_not_a_silent_literal():
    """`{"land": {}}` ber om en ekte landing uten å si hvordan. Det skal kastes."""
    with pytest.raises(ValueError):
        fr.landing_callable({"land": {}}, _landing(), _landing())


def test_empty_lease_object_is_an_error_not_a_silent_passthrough():
    with pytest.raises(ValueError, match="lease.paths"):
        fr.lease_take({"lease": {}}, _evidence())


def test_empty_implement_object_cannot_silently_revert_step_8():
    """Reviewer 2: `{"implement": {}}` gikk stille tilbake til literalen.

    Det gjenopprettet nøyaktig den selv-attesterte målingen BL-4050 fjernet —
    kjeden leste sin egen blast-radius ut av payloaden som ba den kjøre.
    """
    from agent.code_workflow import GovernedCodeRunner

    with pytest.raises(ValueError, match="present but empty"):
        fr.build_callable({"implement": {}, "build": {"changed_files": 1}},
                          GovernedCodeRunner(), _evidence())


def test_the_tick_releases_what_it_took(monkeypatch):
    """Reviewer 1: en lease ingen slipper er trap 3 i lease_authoritys egen fil."""
    released: dict[str, tuple[str, ...]] = {}

    def _release(paths):
        released["paths"] = tuple(paths)
        return True, "sluppet"

    monkeypatch.setattr("agent.lease_authority.release", _release)
    ev = _evidence(source_refs={"lease": "granted/a.py,granted/b.py"})
    note = fr.lease_release({"lease": {"paths": ["x"]}}, ev)
    assert released["paths"] == ("granted/a.py", "granted/b.py")
    assert note == "sluppet"


def test_release_reports_a_failure_instead_of_swallowing_it(monkeypatch):
    monkeypatch.setattr("agent.lease_authority.release",
                        lambda paths: (False, "autoriteten svarte 500"))
    note = fr.lease_release({"lease": {"paths": ["x"]}},
                            _evidence(source_refs={"lease": "a.py"}))
    assert note.startswith("lease IKKE sluppet")


def test_nothing_is_released_when_the_claim_failed(monkeypatch):
    def _never(paths):  # pragma: no cover
        raise AssertionError("slapp en lease som aldri ble tatt")

    monkeypatch.setattr("agent.lease_authority.release", _never)
    note = fr.lease_release({"lease": {"paths": ["x"]}}, _evidence(source_refs={"lease": ""}))
    assert "claimet feilet" in note


def test_the_guard_sees_from_agent_import_x():
    """Reviewer BLOCK 2, som regresjon.

    Vakten matchet bare `agent.X`, saa `from agent import X as y` var USYNLIG.
    Maalt: hele steg-12/13-wiringen kunne slettes uten at ratsjetten roert seg.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_chain_guard", str(REPO / "tests" / "test_chain_is_wired.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    seen = mod._agent_imports("faber_runtime")
    assert "faber_postcommit_adapters" in seen, (
        "vakten ser ikke `from agent import faber_postcommit_adapters as pca` — "
        "da er ratsjetten tilfreds enten ledningen finnes eller ikke")


# ---------------------------------------------------------------------------
# D1 / D2 / D3 — de tre defektene en LIVE kjøring av broen fant (BL-4072-turen)
#
# Alle tre er samme familie som resten av denne fila: et tall eller et svar som
# ser ut som en måling, men som ikke kan bli riktig. Ingen av dem ville blitt
# funnet av en test som bare spurte «kaster den?».
# ---------------------------------------------------------------------------

def _goal(goal_id, scope, **over):
    g = {"goal_id": goal_id, "title": over.pop("title", "et maal"),
         "evidence": {"repo_scope": scope}}
    g.update(over)
    return g


def test_d1_a_goal_that_never_stopped_still_counts_toward_the_depth(monkeypatch):
    """D1: `deepest_step_reached` regnet kun over mål som STOPPET.

    Et mål som planla seg gjennom alt hadde `stopped_at_step is None` og falt
    helt ut av tallet. Målt mot flåtens sju ekte mål — 4 som planla alt, 3 som
    stoppet på steg 1 — rapporterte aggregatet **1**. Linja over den sa at dette
    er tallet som svarer på «virker 13-stegs-flyten»; den svarte på det motsatte,
    fordi jo bedre flyten gikk, jo lavere ble tallet.
    """
    from agent import faber_control_bridge as bridge

    monkeypatch.setattr(bridge, "lease_state_for",
                        lambda scope: {"clear": None, "paths": [], "note": "test"})
    out = bridge.run_all([_goal("g1", "hermes-agent: agent/a.py")], "faber")
    deep = out["deepest_step_reached"]
    assert deep is not None, "et mål som ikke stoppet må telle med i dybden"
    assert deep > 1
    # Og `shallowest_stop` skal fortsatt handle om STOPP — ikke lese den samme
    # lista. Navnet stemte før bare fordi begge var feil på samme måte.
    assert out["shallowest_stop"] is None
    assert out["goals_that_stopped"] == 0


def test_d1_reached_step_never_counts_a_not_executed_step_as_reached(monkeypatch):
    """Den motsatte løgnen er like lett: å telle 13 for et ublokkert mål.

    Steg 6/8/11/12/13 rapporteres NOT_EXECUTED med vilje i tørrkjøringen. Å
    telle dem som nådd ville gjort aggregatet til en påstand om utførelse.
    """
    from agent import faber_control_bridge as bridge
    from agent.faber_control_bridge import DryRunStatus

    monkeypatch.setattr(bridge, "lease_state_for",
                        lambda scope: {"clear": None, "paths": [], "note": "test"})
    result = bridge.run_goal(_goal("g1", "hermes-agent: agent/a.py"), {}, "faber")
    planned = [s["number"] for s in result["steps"]
               if s["status"] == DryRunStatus.PLANNED.value]
    assert result["reached_step"] == max(planned)
    not_executed = {s["number"] for s in result["steps"]
                    if s["status"] == DryRunStatus.NOT_EXECUTED.value}
    assert result["reached_step"] not in not_executed


def test_d2_the_two_scope_parsers_are_now_one():
    """D2: broen godtok ti filformer, autoriteten kun `.py`.

    Samme streng ga to filer hos den ene og «scope navngir ingen filer» hos den
    andre. Skaden var ikke at lease-gaten ble vakuøs — `LandingScopeGate` feiler
    lukket på tomt lease-sett — men at steg 6 ikke KUNNE oppdage en ekte konflikt
    for de scopene, og rapporterte det som et svar.
    """
    from agent.faber_control_bridge import _paths_from_scope
    from agent.lease_authority import scope_paths

    scope = "hermes-agent: agent/x.py, hermes-dashboard.service, docs/kart.md, a.yaml"
    assert list(scope_paths(scope)) == list(_paths_from_scope(scope))
    assert "hermes-dashboard.service" in scope_paths(scope)
    assert "docs/kart.md" in scope_paths(scope)


def test_d2_a_non_python_scope_is_now_askable(monkeypatch):
    """Det målbare utfallet: steg 6 STILLER spørsmålet i stedet for å svare tomt."""
    from agent import faber_control_bridge as bridge

    asked: dict[str, tuple[str, ...]] = {}

    def _check(paths):
        asked["paths"] = tuple(paths)
        return True, "autoritet: 0 av 1 eid, 0 hos andre"

    monkeypatch.setattr("agent.lease_authority.check", _check)
    state = bridge.lease_state_for("hermes-agent: hermes-dashboard.service")
    assert asked["paths"] == ("hermes-dashboard.service",)
    assert state["clear"] is True


def test_d3_mwp_contract_refs_are_a_named_form_not_a_missing_one():
    """D3: MWP-arbeid som siterte sin EGEN ADR korrekt ble straffet for det.

    `CAD-HERMES-*` passerte allerede (CAD-formen er alfanumerisk), men `ADR-` og
    `BL-` var rent numeriske. Så `ADR-HERMES-001` og `BL-MWP-*` ga
    `missing_contract_ref` -> DOUBT -> «IKKE bygg». BL-4029 L6 én etasje opp:
    projeksjonen ble fikset, klassifisereren ikke.
    """
    from agent.task_classifier import parse_contract_ref

    for ref in ("ADR-HERMES-001", "ADR-TRUTH-001-cross-surface-canonical-truth",
                "ADR-H10-SEMANTIC-BOUNDARY-001"):
        assert parse_contract_ref(ref) == "ADR-MWP", ref
    for ref in ("BL-HERMES-9", "BL-MWP-ASI-CRITICAL-PATH-001"):
        assert parse_contract_ref(ref) == "BL-MWP", ref


def test_d3_the_two_registers_do_not_merge():
    """Formnavnet sier HVILKET register. CLAUDE.md: «bland dem aldri».

    Å returnere "ADR" for `ADR-HERMES-001` ville slått Symbioses og MWPs
    nummerserier sammen — og `allocate_adr.py` kjenner ikke MWPs.
    """
    from agent.task_classifier import parse_contract_ref

    assert parse_contract_ref("ADR-061") == "ADR"
    assert parse_contract_ref("BL-4070") == "BL"
    assert parse_contract_ref("ADR-HERMES-001") != "ADR"
    assert parse_contract_ref("BL-MWP-1") != "BL"


def test_d3_a_bare_namespace_prefix_still_buys_nothing():
    """Utvidelsen må ikke bli en ny kontroll-som-ikke-kan-feile.

    `ADR-HERMES` uten identifikator er ikke en navngitt kontrakt, og skal falle
    til DOUBT som før — ellers har D3-fiksen gjenåpnet nøyaktig hullet
    `parse_contract_ref` ble skrevet for å lukke.
    """
    from agent.task_classifier import parse_contract_ref

    for junk in ("ADR-HERMES", "BL-MWP", "ADR-", "BL-HERMES-", "n/a — se ADR-HERMES-001"):
        assert parse_contract_ref(junk) is None, junk


# ---------------------------------------------------------------------------
# Reviewer runde 2, BLOCK 1: lekker `_cli` en lease naar den avbryter?
#
# Claimet skjer foer `build_callable`/`landing_callable`/`postcommit_callable`
# evalueres som argumenter til `tick(...)`. Kaster en av dem — og TO av de
# stiene er BLOCK-1- og BLOCK-4-fiksene fra samme runde — fanget den ytre
# `except` det og returnerte 2 rett forbi `lease_release`. Trap 3 i
# `lease_authority`s egen docstring, gjenopprettet av wiringen som skulle
# lukke den.
# ---------------------------------------------------------------------------

_TICK_BASE = {
    "goal": {"goal_id": "g", "title": "t", "cad_ref": "CAD-1", "adr_ref": "ADR-061",
             "bl_ref": "BL-4070"},
    "evidence": {"git_clean": True, "lease_clear": False, "cad_status": "accepted",
                 "adr_status": "accepted", "bl_status": "open", "obsidian_status": "fresh",
                 "source_refs": {"git": "abc", "lease": "a.py"}},
    "review": {"verdict": "PASS", "diff_id": "d1", "reviewer": "r", "confidence": 0.9},
    "landing": {"commit": "c", "reviewer": "PASS", "tests": "t", "readback": "r",
                "runtime_smoke": "s", "rollback": "b", "brain_change_log": "b",
                "selfstate": "s", "landing_set": ["a.py"]},
    "lease": {"paths": ["a.py"]},
    "build": {"tests": "ok", "diff_id": "d1", "changed_files": 1, "changed_lines": 1},
}


@pytest.mark.parametrize("label,extra", [
    ("exactly-one-brudd", {"postcommit": {"test_paths": ["t.py"]}}),
    ("manglende testmaal", {"postcommit": {"no_runtime_target": "x"}}),
    ("land uten melding", {"land": {}}),
    ("tom implement-spec", {"implement": {}}),
    ("gyldig, men ticken blokkerer", {}),
    # Reviewer runde 3: DENNE kaster INNE i `lease_take`, etter `claim()` — altså
    # utenfor rekkevidden til `finally`-en de fem andre dekket. Testens navn sa
    # «any abort path» mens den ene funksjonen som TAR leasen lå utenfor.
    ("source_refs er ikke en mapping", {"evidence": {**_TICK_BASE["evidence"],
                                                     "source_refs": None}}),
])
def test_the_cli_never_leaks_a_lease_on_any_abort_path(monkeypatch, label, extra):
    import json as _json

    from agent import lease_authority as la

    claimed: list[tuple[str, ...]] = []
    released: list[tuple[str, ...]] = []
    monkeypatch.setattr(la, "claim", lambda paths, ttl=0, note="": (
        claimed.append(tuple(paths)) or la.LeaseOutcome(
            ok=True, acquired=tuple(paths), reason="stub")))
    monkeypatch.setattr(la, "release", lambda paths: (
        released.append(tuple(paths)) or (True, "stub sluppet")))
    monkeypatch.setattr(
        "sys.argv", ["faber_runtime", "--tick-json", _json.dumps({**_TICK_BASE, **extra})])

    fr._cli()
    # INVARIANTEN, og den er formulert som «aldri tatt uten aa bli sluppet» —
    # ikke som «alltid tatt». Reviewer runde 3s sjette tilfelle kaster INNE i
    # `lease_take`, og fiksen flyttet den kastende linja FOER `claim()`. Utfallet
    # er derfor `claimed == released == []`, som er sterkere enn aa slippe: den
    # tar den aldri. En assertion som krevde `claimed` ville felt sin egen fiks.
    assert released == claimed, (
        f"{label}: leasen ble tatt og ikke sluppet — foreldreloes til TTL (3600 s), "
        "og rapporten sier ikke et ord om den")


@pytest.mark.parametrize("label,extra", [
    ("exactly-one-brudd", {"postcommit": {"test_paths": ["t.py"]}}),
    ("gyldig, men ticken blokkerer", {}),
])
def test_the_downstream_abort_paths_really_do_claim_first(monkeypatch, label, extra):
    """Uten denne maaler testen over ingenting paa de stiene som betyr noe.

    Invarianten «aldri tatt uten aa bli sluppet» er trivielt sann naar ingenting
    tas. Denne pinner at de nedstroems avbruddsstiene FAKTISK tar leasen foerst,
    saa slippet er en ekte hendelse og ikke et fravaer.
    """
    import json as _json

    from agent import lease_authority as la

    claimed: list[tuple[str, ...]] = []
    monkeypatch.setattr(la, "claim", lambda paths, ttl=0, note="": (
        claimed.append(tuple(paths)) or la.LeaseOutcome(
            ok=True, acquired=tuple(paths), reason="stub")))
    monkeypatch.setattr(la, "release", lambda paths: (True, "stub sluppet"))
    monkeypatch.setattr(
        "sys.argv", ["faber_runtime", "--tick-json", _json.dumps({**_TICK_BASE, **extra})])
    fr._cli()
    assert claimed == [("a.py",)], label
