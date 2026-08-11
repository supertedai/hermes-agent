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


# ---------------------------------------------------------------------------
# A TIL AA — driveren (BL-4087)
#
# `tests/test_chain_is_wired.py` spor om komponentene er NAABARE. Testene over
# spor om SOEMMENE utfoeres. Disse spor det siste: KALLER noen kjeden i det hele
# tatt? Foer BL-4087 var svaret nei -- `--tick-json` hadde null kallere i cron,
# systemd og skript, mens observe-stien maalte hvert 20. minutt og chat-stien
# raadet paa hver kodende tur. Tre stier, og den som kunne gjoere arbeidet ble
# aldri kalt.
# ---------------------------------------------------------------------------

def _observe_packet(reasons=(), git_ref="deadbeef", gid="g1"):
    return {"observed_at": "2026-08-11T00:00:00Z",
            "observations": [{"goal_id": gid, "reasons": list(reasons),
                              "git_ref": git_ref, "next_step": "bygg noe"}]}


def _registry(gid="g1", *, bl_status="open", scope="hermes-agent: agent/x.py"):
    return [{"goal_id": gid, "title": "koble kjeden", "bl_ref": "BL-4087",
             "cad_ref": "CAD-1", "adr_ref": "ADR-062", "rollback": "git revert",
             "evidence": {"repo_scope": scope, "bl_status": bl_status,
                          "cad_status": "accepted", "adr_status": "accepted"}}]


def _drive_world(monkeypatch, *, head="deadbeef", heads=None, clean=True, dirty=()):
    """Verden slik driveren MAALER den ved drive-tid.

    BL-4087 reviewer BLOCK 2: driveren stoler ikke lenger paa pakken. Den maaler
    HEAD og scope-renheten paa nytt og hopper over hvis verden har flyttet seg
    siden observasjonen. Testriggen maa derfor SI hva verden er -- ellers maaler
    testen bare at treet tilfeldigvis ikke matcher `deadbeef`.
    """
    # `heads` gjoer at de TO lesningene kan gi ulike svar. Reviewer runde 4,
    # BLOCK 3: riggen patchet `git_head` til en KONSTANT, og en konstant kan ikke
    # returnere to verdier — saa den sanne grenen i TOCTOU-vakten var uoppnaaelig
    # i hver eneste test, og aa slette vakten lot 504 tester staa groenne.
    seq = list(heads) if heads else [head]

    def _head(repo):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    monkeypatch.setattr("agent.faber_observe.git_head", _head)
    monkeypatch.setattr("agent.faber_observe.scope_is_clean",
                        lambda repo, scope: (clean, tuple(dirty), 0))


def _stub_lease(monkeypatch, claimed=None, released=None):
    from agent import lease_authority as la

    monkeypatch.setattr(la, "claim", lambda paths, ttl=0, note="": (
        (claimed.append(tuple(paths)) if claimed is not None else None)
        or la.LeaseOutcome(ok=True, acquired=tuple(paths), reason="stub")))
    monkeypatch.setattr(la, "release", lambda paths: (
        (released.append(tuple(paths)) if released is not None else None)
        or (True, "stub sluppet")))


def _write_drive_inputs(tmp_path, packet, registry):
    import json as _json

    p = tmp_path / "observe.json"
    g = tmp_path / "goals.json"
    p.write_text(_json.dumps(packet), encoding="utf-8")
    g.write_text(_json.dumps(registry), encoding="utf-8")
    return str(p), str(g)


def test_only_lease_reasons_are_drivable():
    """Steg 6 fjerner lease-grunnene. Alt annet er en ekte blokkering.

    REVIEWER N2: foerste versjon hardkodet de samme to strengene som
    `_LEASE_ONLY_REASONS`, saa en omformulering i `PreflightGate.evaluate` ville
    holdt testen groenn og gjort driveren til en permanent no-op. Fail-silent,
    ikke fail-safe. Strengene UTLEDES derfor naa ved aa kjoere gaten med evidens
    der kun leasen mangler — hvis gaten omformulerer, feiler denne testen.
    """
    from agent.code_workflow import PreflightGate, PreflightInput

    lease_only = PreflightGate().evaluate(PreflightInput(
        git_clean=True, lease_clear=False, cad_status="accepted",
        adr_status="accepted", bl_status="open", obsidian_status="fresh",
        source_refs={"git": "abc"}, scope_executable=True))
    assert lease_only.reasons, "riggen maalte ingenting — gaten hadde ingen innvending"
    assert fr._drivable(list(lease_only.reasons)), (
        f"gaten sier {lease_only.reasons!r}, men driveren kjenner "
        f"{fr._LEASE_ONLY_REASONS!r} — driveren er naa en no-op")

    assert fr._drivable([])
    assert not fr._drivable(["git target is dirty or has unowned changes"])
    assert not fr._drivable(["target lease is not clear",
                             "scope is not executable on this host: agi"])


def test_the_driver_takes_the_lease_and_gives_it_back(tmp_path, monkeypatch):
    """Steg 6 UTFOERES av driveren -- og etterlater ingen foreldreloes lease."""
    from agent import lease_authority as la

    claimed, released = [], []
    _stub_lease(monkeypatch, claimed, released)
    _drive_world(monkeypatch)
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)

    p, g = _write_drive_inputs(tmp_path, _observe_packet(), _registry())
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert out["driven"] == 1
    assert claimed == [("agent/x.py",)]
    assert released == claimed
    assert out["results"][0]["lease_released"] == "stub sluppet"


def test_the_driver_can_never_fabricate_a_reviewer_pass(tmp_path, monkeypatch):
    """DEN VIKTIGSTE VAKTEN HER.

    En driver som sender `ReviewVerdict.PASS` for aa komme videre, ville vaert
    BL-3673 i en timer: aa skrive en post for aa faa en gate til aa slippe seg
    selv gjennom. Verdikten skal vaere PENDING, og runneren skal blokkere paa
    den -- ingen har DOEMT bygget.
    """
    from agent.code_workflow import ReviewVerdict

    from agent import lease_authority as la

    _stub_lease(monkeypatch)
    _drive_world(monkeypatch)
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)

    seen = {}
    real_tick = fr.FaberRuntime.tick

    def _spy(self, goal, evidence, **kw):
        seen["review"] = kw["review"]({"diff_id": "d1"})
        return real_tick(self, goal, evidence, **kw)

    monkeypatch.setattr(fr.FaberRuntime, "tick", _spy)
    p, g = _write_drive_inputs(tmp_path, _observe_packet(), _registry())
    fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert seen["review"].verdict is ReviewVerdict.PENDING
    assert seen["review"].reviewer == ""
    assert seen["review"].diff_id == "d1", "diff-id-en skal vaere den MAALTE"


def test_shadow_is_by_construction_not_by_flag(tmp_path):
    """`land` og `postcommit` finnes ikke i payloaden i det hele tatt.

    Et skygge-FLAGG kan settes feil. En noekkel som aldri skrives kan ikke det.
    """
    obs = {"goal_id": "g1", "git_ref": "abc", "reasons": [], "next_step": ""}
    payload = fr.payload_for(obs, _registry()[0], repo=str(REPO),
                             build_root=str(tmp_path), test_command=("pytest",))
    assert "land" not in payload
    assert "postcommit" not in payload
    assert payload["implement"]["repo_root"] == str(tmp_path)
    assert payload["evidence"]["source_refs"]["git"] == "abc"


def test_the_build_root_is_never_the_shared_worktree(tmp_path, monkeypatch):
    """Steg 8 SKRIVER filer. Den skal aldri peke paa det delte treet.

    En autonom sloeyfe som skriver inn i et tre aatte stroemmer deler, er
    presist faren `tools/mutation_probe.py` ble skrevet om for aa unngaa.
    """
    from agent import lease_authority as la

    _stub_lease(monkeypatch)
    _drive_world(monkeypatch)

    roots = []

    def _root(repo, into, ref="HEAD"):
        roots.append((repo, into, ref))
        return into

    monkeypatch.setattr(fr, "isolated_build_root", _root)
    p, g = _write_drive_inputs(tmp_path, _observe_packet(git_ref="deadbeef"), _registry())
    fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert roots, "bygget fikk aldri en rot -- testen maalte ingenting"
    for repo, into, ref in roots:
        assert into != repo
        assert str(REPO) not in into
        # Reviewer N1: arkivet tas av den VERIFISERTE shaen, ikke av `HEAD`.
        # Med `HEAD` kunne en parallell commit i vinduet mellom sjekken og
        # arkiveringen gi et bygg mot C mens provenansen sa A.
        assert ref == "deadbeef", (
            "bygget ble arkivert fra noe annet enn shaen driveren nettopp "
            "verifiserte — TOCTOU-vinduet er gjenaapnet")


def test_the_driver_selects_skills_for_the_goal(tmp_path, monkeypatch):
    """TVERS: kjeden spurte aldri skill-velgeren. Naa gjoer den det."""
    from agent import lease_authority as la
    from agent import skill_selector

    _stub_lease(monkeypatch)
    _drive_world(monkeypatch)
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)

    seen = {}

    class _Sel:
        def to_json(self):
            return {"coverage": "complete", "considered": 9,
                    "selected": [{"name": "faber-landing"}]}

    def _spy(task_text, *, stage="unspecified", **kw):
        seen["text"] = task_text
        seen["stage"] = stage
        return _Sel()

    monkeypatch.setattr(skill_selector, "select_for_task", _spy)
    p, g = _write_drive_inputs(tmp_path, _observe_packet(), _registry())
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert seen["stage"] == "chain:drive"
    assert "koble kjeden" in seen["text"] and "BL-4087" in seen["text"]
    assert out["results"][0]["skills_selected"] == ["faber-landing"]
    assert out["results"][0]["skill_coverage"] == "complete"


def test_a_goal_blocked_by_something_step_6_cannot_fix_is_skipped_with_its_reason(tmp_path):
    """Vi fjerner ikke en blokkering ved aa la vaere aa se paa den."""
    p, g = _write_drive_inputs(
        tmp_path,
        _observe_packet(reasons=["scope is not executable on this host: agi"]),
        _registry())
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert out["driven"] == 0 and out["skipped"] == 1
    assert "agi" in out["skipped_detail"][0]["reasons"][0]


def test_a_reserved_bl_stops_the_chain_at_step_5(tmp_path, monkeypatch):
    """Maalt mot de sju ekte maalene: alle har `bl_status=reserved`.

    BL-3673: et RESERVERT nummer betyr at et nummer ble delt ut, ikke at arbeid
    finnes. Kjeden skal stoppe her, og driveren skal IKKE oppgradere statusen
    for aa komme videre.
    """
    from agent import lease_authority as la

    _stub_lease(monkeypatch)
    _drive_world(monkeypatch)
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)

    p, g = _write_drive_inputs(tmp_path, _observe_packet(),
                               _registry(bl_status="reserved"))
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    r = out["results"][0]
    assert r["preflight"] == "PASS", "steg 4 skal aapne — det er steg 5 som stopper"
    assert r["gate"] == "bl_gate"
    assert "reserved" in r["blocker"]

def test_the_driver_refuses_a_packet_observed_against_another_commit(tmp_path, monkeypatch):
    """REVIEWER BLOCK 2: pakken er fra observe-tid, treet fra drive-tid.

    Observe kjoerer :20 og skriver ref A. En parallell stroem commiter -- dette
    treet deles av aatte. Driveren kjoerer paa HEAD = B og ville registrert
    provenans A mens den bygget B, og haevdet scope-renhet maalt mot A.
    """
    _stub_lease(monkeypatch)
    _drive_world(monkeypatch, head="EN-ANNEN-COMMIT")
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)
    p, g = _write_drive_inputs(tmp_path, _observe_packet(git_ref="deadbeef"), _registry())
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert out["driven"] == 0
    assert "flyttet seg" in out["skipped_detail"][0]["why"]
    assert out["skipped_detail"][0]["live_head"] == "EN-ANNEN-COMMIT"


def test_the_driver_refuses_when_the_scope_got_dirty_after_the_observation(tmp_path, monkeypatch):
    _stub_lease(monkeypatch)
    _drive_world(monkeypatch, clean=False, dirty=("agent/x.py",))
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)
    p, g = _write_drive_inputs(tmp_path, _observe_packet(), _registry())
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert out["driven"] == 0
    assert out["skipped_detail"][0]["scope_dirty"] == ["agent/x.py"]


def test_a_packet_without_a_reasons_key_is_not_drivable():
    """`all()` over tomt er vakuoest sant.

    En observasjon UTEN `reasons`-noekkel leste derfor som «helt klar», og da ble
    `git_clean: True` haevdet fra ingenting. Fravaer av en grunnliste er ikke
    fravaer av grunner.
    """
    assert fr._drivable(None) is False


def test_the_payload_carries_the_refs_steps_5_and_7_actually_read(tmp_path):
    """REVIEWER BLOCK 1, som regresjon.

    `BlGate` krever `bl`, `DesignGate` krever `cad` og `adr`. Foerste utkast
    skrev bare `git` og `lease`, saa INGEN legitim handlingssekvens kunne aapne
    steg 5 eller 7 -- muren var flyttet, ikke fjernet.
    """
    obs = {"goal_id": "g1", "git_ref": "abc", "reasons": [], "next_step": ""}
    refs = fr.payload_for(obs, _registry()[0], repo=str(REPO),
                          build_root=str(tmp_path), test_command=())["evidence"]["source_refs"]
    assert refs["bl"] == "BL-4087"
    assert refs["cad"] == "CAD-1"
    assert refs["adr"] == "ADR-062"
    assert refs["git"] == "abc"


def test_a_goal_without_cad_or_adr_reaches_step_7_and_blocks_there(tmp_path, monkeypatch):
    """Beviset reviewer krevde: muren staar i VERDEN, ikke i koden.

    Maalt paa den levende backloggen: alle sju maal baerer `cad_ref=""` og
    `adr_ref=""`. Med en handlingsbar BL naar kjeden derfor steg 7 og blokkerer
    der -- paa et ekte fravaer, ikke paa en droppet payload-noekkel.
    """
    _stub_lease(monkeypatch)
    _drive_world(monkeypatch)
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)

    reg = _registry(bl_status="open")
    reg[0]["cad_ref"] = ""
    reg[0]["adr_ref"] = ""
    p, g = _write_drive_inputs(tmp_path, _observe_packet(), reg)
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    r = out["results"][0]
    assert r["preflight"] == "PASS", "steg 4 skal aapne"
    # OG HER ER FUNNET, som ikke var det jeg antok da jeg skrev testen.
    # Fravaeret av CAD/ADR fanges -- men av LEDGEREN, som et unntak fra
    # `FaberGoalLedger.transition` ("goal references required before build"),
    # ikke av `DesignGate` (steg 7). Overgangsvakten fyrer foer gaten, saa den
    # gaten som FINNES for nettopp dette kjoerer aldri. Konsekvensen er synlig i
    # utfallet: `gate="runner"` og `next_step="inspect and retry"` -- en
    # next_step som ikke navngir en handling, som er den ene tingen BL-4029 sa
    # den alltid skal gjoere.
    #
    # Registrert som G12 i BL-HERMES-CHAIN-DRIVE-001. Aa flytte gate-rekkefoelgen
    # i runneren er en egen beslutning med egen review; testen pinner derfor det
    # SANNE utfallet, ikke det jeg haapet paa.
    assert r["gate"] == "runner", r
    assert "cad_ref" in r["blocker"] and "adr_ref" in r["blocker"], r["blocker"]
    assert r["next_step"] == "inspect and retry", (
        "naar dette endrer seg har noen flyttet sjekken til DesignGate — "
        "oppdater G12 i BL-HERMES-CHAIN-DRIVE-001 sammen med den endringen")


def test_isolated_build_root_actually_archives_the_given_sha(tmp_path):
    """G5, MAALT — ikke lenger paastaatt. (reviewer runde 3, BLOCK 2)

    `isolated_build_root` var monkeypatchet i ALLE aatte testbruk, saa den ble
    aldri utfoert. Den forrige vakten sammenlignet `ref` mot en STUB hvis default
    speilet den ekte signaturen — den testet altsaa ikke arkivet i det hele tatt,
    og en mutasjon i selve kroppen (`ref` -> `"HEAD"`) lot 62 mutanter og 605
    tester staa groenne.

    Dette er den lastbaerende sikkerhetsegenskapen i ADR-ens Decision 1: fremmede
    UKOMMITTERTE filer er FYSISK FRAVAERENDE fra treet bygget og testene kjoerer i.
    Det er den som avviser BL-3643-moteksempelet, og den hadde null dekning.
    """
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,  # noqa: E731
                                    capture_output=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f.py").write_text("GAMMEL\n", encoding="utf-8")
    run("add", "f.py")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a")
    sha_a = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    (repo / "f.py").write_text("NY\n", encoding="utf-8")
    run("add", "f.py")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b")
    # En fremmed, UKOMMITTERT fil — den parallelle stroemmens arbeid.
    (repo / "andres_ukommitterte.py").write_text("import noe_som_ikke_finnes\n",
                                                 encoding="utf-8")

    into = tmp_path / "kopi"
    root = fr.isolated_build_root(str(repo), str(into), sha_a)

    from pathlib import Path

    assert (Path(root) / "f.py").read_text(encoding="utf-8").strip() == "GAMMEL", (
        "arkivet fulgte HEAD i stedet for shaen som ble oppgitt — TOCTOU-vinduet "
        "er aapent igjen")
    assert not (Path(root) / "andres_ukommitterte.py").exists(), (
        "en parallell stroems ukommitterte fil havnet i byggetreet — det er "
        "BL-3643-moteksempelet, og hele grunnen scope-relativ renhet er trygg")


def test_isolated_build_root_refuses_an_unknown_ref(tmp_path):
    """En ugyldig sha skal KASTE, ikke stille falle tilbake paa HEAD."""
    import subprocess

    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f.py").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "f.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "a"], check=True, capture_output=True)
    with pytest.raises(RuntimeError, match="git archive feilet"):
        fr.isolated_build_root(str(repo), str(tmp_path / "ut"), "0" * 40)


def test_a_commit_landing_while_cleanliness_is_measured_skips_the_goal(tmp_path, monkeypatch):
    """BLOCK 3: den ANDRE HEAD-lesningen, som ingenting daekket.

    Rekkefoelgen er `git_head` -> `scope_is_clean` -> `git_head` -> `archive`.
    Uten den andre lesningen kunne en commit lande mellom de to foerste, slik at
    renheten ble maalt mot én tilstand og arkivet tatt av en annen. Arkivets
    INNHOLD var allerede laast av `ref`; dette laaser KORRESPONDANSEN.

    Testen lar de to lesningene gi ulike svar — noe riggens konstant ikke kunne.
    """
    _stub_lease(monkeypatch)
    _drive_world(monkeypatch, heads=["deadbeef", "EN-ANNEN-COMMIT"])
    monkeypatch.setattr(fr, "isolated_build_root",
                        lambda repo, into, ref="HEAD": into)
    p, g = _write_drive_inputs(tmp_path, _observe_packet(git_ref="deadbeef"), _registry())
    out = fr.drive_from_observe(p, g, repo=str(REPO), limit=1)
    assert out["driven"] == 0
    assert "flyttet seg mens renheten ble maalt" in out["skipped_detail"][0]["why"]


def test_the_bridge_readback_carries_the_whole_handoff_contract(monkeypatch):
    """En blokkering uten eier og uten navngitt neste handling er en melding
    ingen kan handle paa.

    Readbacken sa HVOR og HVORFOR, men ikke HVEM som eier det, hvilken evidens
    som er knyttet til, eller HVA neste handling er. Alle tre laa alt i
    `ControlTask` -- de var bare ikke projisert ut.
    """
    from agent import faber_control_bridge as bridge

    monkeypatch.setattr(bridge, "lease_state_for",
                        lambda scope: {"clear": None, "paths": [], "note": "test"})
    out = bridge.run_all([{
        "goal_id": "g1", "title": "t", "owner": "faber", "bl_ref": "BL-4095",
        "adr_ref": "ADR-HERMES-CHAIN-DRIVE-001",
        "evidence": {"repo_scope": "hermes-agent: agent/x.py"},
    }], "faber")
    r = out["results"][0]
    assert r["owner"] == "faber"
    assert "BL-4095" in r["evidence_refs"]
    assert r["next_action"], "en readback uten neste handling navngir ingen handling"
    assert "owners_blocking" in out


def test_a_blocked_goal_names_the_owner_that_must_act(monkeypatch):
    from agent import faber_control_bridge as bridge

    monkeypatch.setattr(bridge, "lease_state_for",
                        lambda scope: {"clear": None, "paths": [], "note": "test"})
    out = bridge.run_all([{
        "goal_id": "g1", "title": "flytt hard-limit for landing", "owner": "faber",
        # `gate` gir `required_gate`, som gir OWNER_GATE, som gjoer `permitted`
        # falsk -- og DA blokkerer `dry_run_13_step` paa steg 1. Uten det ble
        # raden aldri blokkert, og testen maalte ingenting.
        "evidence": {"repo_scope": "hermes-agent: hermes-dashboard.service",
                     "gate": "morten"},
    }], "faber")
    r = out["results"][0]
    # UBETINGET. Foerste utkast la alt under `if r["stopped_at_step"]:`, og for
    # det maalet var den None -- saa testen utfoerte NULL assertions mens navnet
    # paastod at den bandt eierskap paa en blokkert rad.
    assert r["stopped_at_step"], (
        "riggen produserte ikke en blokkert rad — testen ville maalt ingenting")
    assert r["owner"] == "faber", r
    # DEN AVGJOERENDE: eier og blokkerende part er ULIKE her, som i alle tre
    # ekte blokkerte maal (`owner=faber`, `required_gate=morten`). Foerste
    # utkast hadde owner == gate i riggen, saa `owners_blocking` kunne
    # projisere FEIL felt og likevel passere — og gjorde det: mot de sju ekte
    # maalene svarte den `faber`, altsaa agenten selv.
    assert r["blocked_by"] == "morten", r
    assert out["owners_blocking"] == ["morten"], out["owners_blocking"]
    # INNHOLDET, ikke bare at feltet er ikke-tomt. Mutasjonsproben viste at en
    # ikke-tom-sjekk passerte selv naar feltet ble lest fra feil objekt, fordi
    # fallbacken gjorde den ikke-tom uansett.
    assert r["next_action"] != r["stopped_reason"], (
        f"next_action er bare en omskrivning av blokkeringen: {r['next_action']!r}")
    assert "resolve blockers" in r["next_action"] or "discovery" in r["next_action"], r


def test_an_incomplete_design_is_refused_before_it_is_stored(tmp_path):
    """`assert_actionable()` foer lagring, ikke ett steg senere.

    Uten den blokkerer steg 8 med en generisk grunn paa noe steg 7 skulle ha
    fanget -- og designet ligger allerede i butikken naar det skjer.
    """
    from agent.faber_implementer import ImplementationBlocked

    with pytest.raises(ImplementationBlocked, match="not actionable"):
        fr.author_design({"goal_id": "g", "design": "noe"},
                         design_root=str(tmp_path))
    assert not list(tmp_path.rglob("*.json")), "et ugyldig design ble lagret"


def test_the_builder_route_names_model_url_and_role_explicitly(tmp_path):
    """Den farlige: uten EKSPLISITT modell resolver rollen til Luna.

    `builder`, `builder_120b` og `builder` peker alle til `gpt-5.6-luna` via
    Hermes-konfigurasjonens default. Droppes `cortex_model`, sendes altsaa en
    Luna-forespoersel til `.12:8002` -- en vert som ikke serverer Luna -- og
    kallet feiler paa feil modell, ikke paa noe leseren kan se.
    """
    obs = {"goal_id": "g1", "git_ref": "abc", "reasons": [], "next_step": ""}
    spec = fr.payload_for(obs, _registry()[0], repo=str(REPO),
                          build_root=str(tmp_path), test_command=())["implement"]
    assert spec["cortex_model"], "modellen maa vaere eksplisitt, ikke resolvert"
    assert spec["cortex_url"], "endepunktet maa foelge modellen"
    assert spec["cortex_role"], "rollen maa staa, saa loggen viser hvilken rute"
    # Og den maa faktisk naa generatoren.
    from agent.code_workflow import GovernedCodeRunner
    seen = {}

    import agent.faber_implementer as fi
    real = fi.CortexPatchGenerator

    class _Spy(real):
        def __init__(self, **kw):
            seen.update(kw)
            super().__init__(**kw)

    built = {}
    real_bound = fi.FaberImplementer.bound_to

    @classmethod
    def _capture(cls, runner, **kw):
        impl = real_bound.__func__(cls, runner, **kw)
        built["implementer"] = impl
        return impl

    fi.CortexPatchGenerator = _Spy
    fi.FaberImplementer.bound_to = _capture
    try:
        fr.build_callable({"implement": spec}, GovernedCodeRunner(),
                          _evidence(source_refs={"lease": "agent/x.py"}))
    finally:
        fi.CortexPatchGenerator = real
        fi.FaberImplementer.bound_to = real_bound

    assert seen.get("model") == spec["cortex_model"], seen
    assert seen.get("base_url") == spec["cortex_url"], seen
    assert seen.get("role") == spec["cortex_role"], seen
    # OG AT IMPLEMENTEREN FAKTISK HOLDER DEN. Foerste utkast bygde spionen og
    # sjekket hva den ble bygget MED -- ikke at den naadde utfoereren. Slettes
    # `generator=generator,` faller `FaberImplementer` tilbake paa
    # `CortexPatchGenerator()` med default-rollen, altsaa Luna mot en vert som
    # ikke serverer Luna. Testen passerte med den linja borte.
    impl = built.get("implementer")
    assert impl is not None, "bound_to ble aldri kalt — testen maalte ingenting"
    assert isinstance(impl.generator, _Spy), (
        "utfoereren holder en annen generator enn den ruten bygde — "
        "byggeruten naar ikke steg 8")
    assert impl.generator.model == spec["cortex_model"]
    assert impl.generator.base_url == spec["cortex_url"].rstrip("/")


def test_a_goal_blocked_by_its_own_state_names_no_party(monkeypatch):
    """Terminal tilstand: INGEN part kan handle, og da skal ingen navngis.

    Reviewer viste at `or task.owner`-fallbacken gjeninnfoerte BLOCK 1 her: et
    maal i `BLOCKED` har tomt `required_gate`, saa aggregatet svarte `faber` --
    agenten selv. Fire av de sju levende maalene baerer `gate: reviewer`, som
    gir tomt `required_gate`, og staar én tilstandsendring fra dette.
    """
    from agent import faber_control_bridge as bridge

    monkeypatch.setattr(bridge, "lease_state_for",
                        lambda scope: {"clear": None, "paths": [], "note": "test"})
    out = bridge.run_all([{
        "goal_id": "g1", "title": "t", "owner": "faber", "state": "blocked",
        "evidence": {"repo_scope": "hermes-agent: agent/x.py", "gate": "reviewer"},
    }], "faber")
    r = out["results"][0]
    assert r["stopped_at_step"], "riggen produserte ikke en blokkert rad"
    assert r["blocked_by"] == "", (
        f"tilstanden blokkerer, ingen part kan laase opp — men feltet sier "
        f"{r['blocked_by']!r}")
    assert out["owners_blocking"] == [], out["owners_blocking"]


def test_the_bridge_uses_one_control_plane_instance():
    """ÉN instans. Kontrollplanet sammenligner enums med `is`.

    To `exec_module`-kall gir to modulobjekter, og da beregnes `OWNER_GATE` --
    den ene verdikten som ruter til Morten -- som vanlig `BLOCK`.
    """
    from agent import faber_control_bridge as bridge

    assert bridge._CP is bridge._cp, (
        "broen holder to kontrollplan-instanser; enum-identitet brytes")
    assert bridge._CP.TaskState is bridge._cp.TaskState
