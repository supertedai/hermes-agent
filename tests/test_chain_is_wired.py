"""Er de sju komponentene KOBLET, eller bare til stede? (BL-4066)

Sju parallelle oekter bygde sju komponenter paa én morgen. Hver av dem har egne
tester, hver fikk reviewer-PASS, og hver av dem er riktig. Likevel:

    MAALT 2026-08-11 mot HEAD 568ddf03f
      faber_runtime.py importerer 0 av 7
      faber_landing (steg 11s utfoerer)        0 importoerer
      second_opinion.resolve_disagreement      aldri kalt   <- LUKKET siden;
                                               code_workflow.py kaller den naa
      faber_runtime.py:213                     landing=lambda _: landing

Det er MOENSTERET som gaar igjen i hele dette systemet, og som er navngitt i
grafen: **systemet er flinkere til aa skrive kontrakter enn til aa koble dem.**
`ScopeBudget` fantes uten kallere. Tre av fire MWP-gater hadde ingen. `BlGate` og
`DesignGate` var skrevet, aldri spurt. `LandingEvidence` manglet fillisten sjekken
trengte. Hver gang oppdaget av at NOEN saa etter -- aldri av en test.

Denne fila er den testen. Den bor bevisst ikke inne i noen av de sju modulene,
fordi defekten ikke bor i noen av dem: hver er korrekt for seg. Den bor i SOEMMEN,
og en soem uten vakt er der arbeid forsvinner.

## `xfail(strict=True)`, og hvorfor det ikke er aa gjemme noe

Aa lande seks ROEDE tester i et tre der aatte oekter arbeider ville gjort suiten
roed for alle, og en permanent roed suite slutter folk aa lese. Markoeren er
`strict=True`, som betyr: **naar gapet lukkes, FEILER testen** (XPASS er en feil),
og den som lukket det blir tvunget til aa fjerne markoeren. Gapet kan altsaa ikke
lukkes i stillhet, og det kan ikke bli staaende i stillhet heller.

Det er den motsatte egenskapen av en vanlig `skip`: en skip forsvinner, en strict
xfail insisterer paa aa bli ryddet.

## Hvorfor den er roed naar den skrives

Den er skrevet FOER wiringen finnes, med vilje. En integrasjonstest lagt til
ETTER at koblingen er gjort, beviser bare at koblingen var der da noen sist saa
etter. Skrevet foerst, er den en aksept-kriterium: den blir groenn naar arbeidet
er ferdig, og ikke foer.

De to filene wiringen maa inn i -- `agent/faber_runtime.py` og
`agent/code_workflow.py` -- er leaset av parallelle oekter (BL-4050, BL-4052) mens
dette skrives. Testen er derfor formulert mot MODULGRENSENE, ikke mot linjer, saa
den taaler at de to landes i hvilken som helst rekkefoelge.

## TRE MAATER DENNE VAKTEN KAN LYVE PAA (reviewer, punkt v)

Skrevet ned fordi en vakt som roper ulv blir slettet, og da gjenaapner gapet den
voktet uten at noen ser det. Faar du et roedt resultat, sjekk disse foerst:

1. **Relative importer.** `_agent_imports` matcher kun absolutt `agent.X`. En
   refaktorering til `from .faber_landing import …` leser som UKOBLET. Stilen
   finnes allerede i treet (`agent/__init__.py`, `agent/monitoring/__init__.py`).
2. **Pakke-konvertering.** Blir en komponent til `agent/faber_landing/__init__.py`,
   er `is_file()` paa `.py` False, og eksistens-testen melder den som SLETTET.
3. **Dynamisk wiring.** `importlib.import_module` eller registry-dispatch er
   usynlig for AST og leses som ukoblet.

Alle tre gir FALSKE ukoblet-funn, aldri falske koblet-funn. Feilretningen er
altsaa trygg — vakten kan mase, den kan ikke sove.

## Hva den IKKE gjoer

Den kjoerer ikke kjeden og lander ingenting. Den spoer ett spoersmaal per komponent:
*finnes det en importsti fra runtimen til deg?* Det er et svakt krav -- en import
er ikke et kall -- men det er det svakeste kravet som ikke kan oppfylles ved et
uhell, og det fanger nettopp den tilstanden som har oppstaatt sju ganger i dag.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

#: Komponentene som ble bygget for kjeden, og steget hver av dem eier.
#: `None` betyr at komponenten ikke hoerer til ett bestemt steg.
CHAIN_COMPONENTS = {
    "task_classifier": "steg 3 — BL eller ADR",
    "lease_authority": "steg 6 — ta leasen",
    "faber_implementer": "steg 8 — bygg",
    "second_opinion": "steg 10 — andre mening",
    "faber_landing": "steg 11 — land",
    "faber_postcommit_adapters": "steg 12/13 — roeyktest og tilbakelesing",
    "skill_selector": "tvers — velg skill for oppgaven",
}

#: Kjedens egne innganger -- det som kjoerer NAAR et maal behandles.
CHAIN_ENTRYPOINTS = ("faber_runtime", "faber_control_bridge", "code_workflow")

#: SCHEDULERTE innganger. Maalt i `agent@192.168.40.15`s crontab 2026-08-11:
#:   */20 * * * *  python -m agent.faber_observe --record …
#:   */20 * * * *  python -m agent.faber_goal_state --from-observe …
#:   */20 * * * *  tools/faber_activation_todo_tick.py
#:
#: DE MAA MED, og grunnen er en feil jeg naesten skrev inn i denne vakten: uten
#: dem meldte den `lease_authority` som UKOBLET. Den er importert av
#: `faber_observe`, som kjoerer hvert tjuende minutt. Vakten ville altsaa
#: rapportert LEVENDE kode som doed -- noeyaktig den falske-funn-klassen den
#: finnes for aa hindre, og samme feil som `.11`-crontab-blindheten i CLAUDE.md:
#: fravaer av LOKAL kaller beviser ikke fravaer av kjoering.
#:
#: Skillet mellom de to listene er selve poenget. En komponent naadd KUN herfra
#: er live, men utenfor kjeden -- et eget funn, ikke en feil.
SCHEDULED_ENTRYPOINTS = ("faber_observe", "faber_goal_state")

#: GATEWAY-flaten. `faber_live_adapter` naas fra `tui_gateway/methods_prompt.py`,
#: som naas fra `tui_gateway/server.py` -- en LEVENDE flate. Uten denne kategorien
#: meldte vakten `skill_selector` som «bygget, men ikke koblet» mens den kjoerer.
#: Det er `lease_authority`-naerbommen om igjen, ett lag ut: cron-fiksen dekket
#: schedulerte innganger og ikke gateway-en.
#:
#: **Tre kategorier, fordi det finnes tre svar.** «Ikke i kjeden» og «ikke i bruk»
#: er ulike funn med ulike neste-handlinger, og en vakt som slaar dem sammen
#: sender folk paa jakt etter doed kode som er i drift.
GATEWAY_MODULES = ("faber_live_adapter",)

#: Kataloger en kaller kan bo i. Kjeden spenner flere flater enn `agent/`.
CALLER_SURFACES = ("agent", "hermes_cli", "tui_gateway", "tools")


class UnreadableModule(RuntimeError):
    """En modul kunne ikke leses. IKKE det samme som «importerer ingenting».

    Skillet er hele forskjellen mellom «komponenten er ikke koblet» og «jeg fikk
    ikke lest etter». Bare den foerste er et funn.
    """


def _agent_imports(module: str) -> set[str]:
    """Hvilke `agent.*`-moduler importerer `module`? Lest med AST, ikke regex.

    Regex paa importlinjer teller docstring-omtaler og kommentarer med. Det er
    presis feilen som fikk meg til aa rapportere `RuntimeSmokeGate` som «kalt av
    task_classifier» da den bare var NEVNT der. AST ser bare ekte importer.
    """
    path = REPO / "agent" / f"{module}.py"
    if not path.is_file():
        raise UnreadableModule(f"{module}: fila finnes ikke ({path})")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError) as exc:
        # FUNNET I MIN EGEN VAKT, under mutasjonstesting: her sto ingenting, saa
        # en fil som ikke lot seg lese ga TOM MENGDE -- og tom mengde leses av
        # kalleren som «importerer ingenting», altsaa «ikke koblet».
        #
        # Vakten mot «bygget, men ikke koblet» hadde selv formen «fravaer av data
        # rapportert som et positivt funn». En uleselig fil under refaktorering
        # ville produsert fire falske ukoblet-funn og pekt paa feil aarsak.
        #
        # Naa kaster den. Kan vi ikke lese, VET vi ikke, og det skal se ut som
        # noe annet enn et svar.
        raise UnreadableModule(f"{module}: kunne ikke parses — {type(exc).__name__}: {exc}") from exc
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("agent."):
                out.add(node.module.split(".", 1)[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("agent."):
                    out.add(alias.name.split(".", 1)[1])
    return out


def _reachable_from(roots, max_depth: int = 2) -> set[str]:
    """Moduler kjedens innganger naar, i inntil `max_depth` hopp.

    To hopp og ikke ubegrenset: en komponent som bare naas via fem mellomledd er
    ikke koblet TIL KJEDEN paa noen meningsfull maate -- den er koblet til noe som
    tilfeldigvis deler prosess. Grensen er en paastand om arkitektur, ikke en
    ytelsesoptimalisering, og den skal vaere stram nok til aa vaere falsifiserbar.
    """
    seen: set[str] = set()
    frontier = set(roots)
    for _ in range(max_depth):
        nxt: set[str] = set()
        for mod in frontier:
            if not (REPO / "agent" / f"{mod}.py").is_file():
                # En inngang i listen som ikke finnes er en foreldet KONSTANT, ikke
                # en uleselig fil. Den hoppes over her og fanges av egen test under.
                continue
            for dep in _agent_imports(mod):
                if dep not in seen:
                    seen.add(dep)
                    nxt.add(dep)
        frontier = nxt
    return seen


def test_every_component_exists_before_we_ask_whether_it_is_wired():
    """Rekkefoelgen er poenget: «finnes ikke» og «finnes, ukoblet» er ulike funn.

    Uten dette ville en slettet modul lest som en ukoblet én, og fiksen for de to
    er ikke den samme.
    """
    missing = [m for m in CHAIN_COMPONENTS if not (REPO / "agent" / f"{m}.py").is_file()]
    assert not missing, f"komponenter som ikke finnes: {missing}"


#: MAALT 2026-08-11 mot HEAD 568ddf03f. Hver linje er et aapent gap, ikke en
#: unntaksregel -- og `strict` gjoer at den ikke kan bli staaende naar den lukkes.
_KNOWN_UNWIRED = {
    "faber_landing": "steg 11s utfoerer har null importoerer; runtimen forsyner "
                     "fortsatt `landing=lambda _: landing`",
    "faber_postcommit_adapters": "steg 12/13 bygget av BL-4052, wiringen ligger "
                                 "ukommittert i en leaset fil",
    "lease_authority": "LIVE via faber_observe (*/20 cron), men utenfor kjeden — "
                       "kjeden KREVER en lease to steder og tar den ingen steder",
    # LIVE via gateway (tui_gateway -> faber_live_adapter), men kjeden selv
    # spoer den ikke. Kategorien over sier det; teksten her maa si det samme.
    "skill_selector": "LIVE via gateway-flaten, men ingen i KJEDEN spoer den",
}


@pytest.mark.parametrize("module,step", sorted(CHAIN_COMPONENTS.items()))
def test_the_chain_can_reach_every_component_it_was_given(module: str, step: str, request):
    """Kjeden maa kunne NAA hver komponent som ble bygget for den.

    Feiler denne, er komponenten en OEY: bygget, testet, reviewet, landet -- og
    utenfor rekkevidde for det som faktisk kjoerer. Det er ikke en halvferdig
    kobling, det er ingen kobling, og forskjellen er usynlig i en groenn suite for
    komponenten selv.
    """
    if module in _KNOWN_UNWIRED:
        request.node.add_marker(pytest.mark.xfail(
            strict=True, reason=f"BL-4066 aapent gap: {_KNOWN_UNWIRED[module]}"))
    from_chain = _reachable_from(CHAIN_ENTRYPOINTS)
    from_cron = _reachable_from(SCHEDULED_ENTRYPOINTS)
    from_gateway = _reachable_from(GATEWAY_MODULES) | set(GATEWAY_MODULES)
    if module in from_chain:
        return
    assert module not in from_gateway, (
        f"{module} ({step}) naas fra GATEWAY-flaten, ikke fra kjeden. Den er "
        f"LIVE — ikke let etter doed kode."
    )
    assert module not in from_cron, (
        f"{module} ({step}) naas KUN fra en schedulert inngang "
        f"({' / '.join(SCHEDULED_ENTRYPOINTS)}), ikke fra kjeden. Den er LIVE, "
        f"men utenfor kjeden — et eget funn, ikke doed kode."
    )
    raise AssertionError(
        f"{module} ({step}) naas hverken fra kjeden "
        f"({' / '.join(CHAIN_ENTRYPOINTS)}) eller fra en schedulert inngang — "
        f"bygget, men ikke koblet"
    )


@pytest.mark.xfail(strict=True, reason="BL-4066 aapent gap: faber_runtime:213 forsyner landings-stubben")
def test_the_landing_callback_is_not_a_stub():
    """`landing=lambda _: landing` returnerer det den fikk. Den lander ingenting.

    Steg 11s vakt (`LandingScopeGate`) kan doemme en landing; utfoereren
    (`faber_landing`) kan utfoere én. Mellom dem sto en lambda som ga tilbake sitt
    eget argument, og BEGGE sider saa riktige ut hver for seg.
    """
    src = (REPO / "agent" / "faber_runtime.py").read_text(encoding="utf-8")
    assert "landing=lambda _: landing" not in src, (
        "faber_runtime forsyner fortsatt landings-stubben; "
        "faber_landing er bygget og ubrukt"
    )


def test_a_second_opinion_is_actually_requested_somewhere():
    """En andre mening som aldri BES OM er ikke en kontroll, den er en modul.

    `assert_independent` brukes -- men det er hjelperen som sjekker at vurdereren
    er uavhengig, ikke kallet som henter vurderingen. Å bruke hjelperen og aldri
    stille spoersmaalet er den samme formen som en gate uten kallere.
    """
    # BLOCK-2 (reviewer): foerste versjon skannet KUN `agent/`, og den ekte
    # kalleren laa i `hermes_cli/web_server.py`. En vakt som ser i én katalog og
    # konkluderer om hele repoet, melder en lukket kobling som aapen for alltid.
    # Kjeden spenner flere flater; skanningen maa spenne de samme.
    callers = []
    for path in sorted(q for d in CALLER_SURFACES for q in (REPO / d).rglob("*.py")):
        if path.stem == "second_opinion":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "agent.second_opinion":
                if any(a.name == "resolve_disagreement" for a in node.names):
                    callers.append(path.name)
    assert callers, (
        "second_opinion.resolve_disagreement har ingen kallere — "
        "andre-meningen er bygget, men ingen ber om den"
    )


def test_every_named_entrypoint_actually_exists():
    """En inngang som er slettet ville stille krympet det vakten ser.

    Uten denne kunne `CHAIN_ENTRYPOINTS` raatne til et navn som ikke finnes, og
    hver komponent ville da meldes ukoblet av en grunn som ikke hadde noe med
    koblingen aa gjoere.
    """
    missing = [e for e in CHAIN_ENTRYPOINTS + SCHEDULED_ENTRYPOINTS
               if not (REPO / "agent" / f"{e}.py").is_file()]
    assert not missing, f"navngitte innganger som ikke finnes: {missing}"


def test_an_unreadable_module_raises_instead_of_reading_as_unwired(tmp_path, monkeypatch):
    """Vakten maa ikke kunne forveksle «fikk ikke lest» med «ikke koblet».

    Dette er defekten jeg fant i vakten selv: `ast.parse` uten feilhaandtering ga
    tom mengde paa en uleselig fil, og tom mengde er umulig aa skille fra «denne
    modulen importerer ingenting».
    """
    fake = tmp_path / "agent"
    fake.mkdir()
    (fake / "kaputt.py").write_text("def (\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    with pytest.raises(UnreadableModule) as exc:
        _agent_imports("kaputt")
    assert "kunne ikke parses" in str(exc.value)
