"""Er kjedens komponenter KOBLET, eller bare til stede? (BL-4066 / BL-4069)

Sju parallelle oekter bygde sju kjede-komponenter paa én morgen. Hver har egne
tester og egen reviewer-PASS. Hver er korrekt alene. Likevel naadde runtimen
null av dem, steg 11s utfoerer hadde null importoerer, og runtimen forsynte
fortsatt sin landings-stubb.

Ingen av de sju testene kunne fange det, fordi ingen av de sju var feil.

FEILKLASSEN ER GJENTAGENDE: `ScopeBudget` fantes uten kallere. Tre av fire
MWP-gater hadde ingen. `BlGate` og `DesignGate` var skrevet, aldri spurt.
`LandingEvidence` manglet fillisten sin egen sjekk trengte. Hver gang oppdaget
av at NOEN saa etter -- aldri av en test. Denne fila er den testen, og den bor i
SOEMMEN med vilje: defekten bor i ingen av delene.

## BL-4069: hvorfor de harde markoerene ble til en RATSJETT

Foerste versjon hardkodet hvilke komponenter som var ukoblet, kalibrert mot ett
oeyeblikksbilde av ARBEIDSTREET. Maalt rett etterpaa:

    arbeidstreet   7 passed, 5 xfailed
    HEAD           2 failed, 6 passed, 4 xfailed

Vakten leser arbeidstreet; CI kjoerer HEAD. Jeg landet altsaa en vakt som var
ROED for alle andre enn meg. Og med aatte oekter som lander wiring lopende er
ETHVERT oeyeblikksbilde utdatert foer commiten er skrevet. En liste som maa
vedlikeholdes raskere enn den kan leses, blir slaatt av.

RATSJETTEN teller hvor mange komponenter kjeden IKKE naar, og krever at tallet
aldri OEKER. Aa lande wiring senker det. Ingenting kan heve det uten at noen
endrer `MAX_UNREACHED` -- og da er det et vedtak, ikke et uhell. Den er
ufoelsom for rekkefoelgen de aatte oektene lander i.

PRISEN, sagt hoeyt: ratsjetten fanger ikke at komponent A kobles mens B kobles
FRA i samme commit -- summen staar stille. Derfor skriver testen ut hele kartet
ved hver kjoering, saa en slik bytte er synlig for et menneske selv naar tallet
ikke roerer seg. Et tall alene er en svakere paastand enn en liste, og det skal
staa her hvilken av dem du faar.

## TRE MAATER DENNE VAKTEN KAN LYVE PAA

En vakt som roper ulv blir slettet, og da gjenaapner gapet den voktet uten at
noen ser det. Faar du et uventet resultat, sjekk disse foerst:

1. **Relative importer.** `_agent_imports` matcher kun absolutt `agent.X`. En
   refaktorering til `from .faber_landing import ...` leser som UKOBLET. Stilen
   finnes allerede i treet.
2. **Pakke-konvertering.** Blir en komponent til `agent/X/__init__.py`, er
   `is_file()` paa `.py` False, og eksistens-testen melder den som SLETTET.
3. **Dynamisk wiring.** `importlib.import_module` eller registry-dispatch er
   usynlig for AST og leses som ukoblet.

Alle tre gir FALSKE ukoblet-funn, aldri falske koblet-funn. Feilretningen er
trygg: vakten kan mase, den kan ikke sove.

## Hva den ikke gjoer

Den kjoerer ikke kjeden og lander ingenting. Den spoer ett spoersmaal per
komponent: *finnes det en importsti fra kjeden til deg?* En import er ikke et
kall -- men det er det svakeste kravet som ikke kan oppfylles ved et uhell.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

#: Komponentene som ble bygget for kjeden, og steget hver eier.
CHAIN_COMPONENTS = {
    "task_classifier": "steg 3 - BL eller ADR",
    "lease_authority": "steg 6 - ta leasen",
    "faber_implementer": "steg 8 - bygg",
    "second_opinion": "steg 10 - andre mening",
    "faber_landing": "steg 11 - land",
    "faber_postcommit_adapters": "steg 12/13 - roeyktest og tilbakelesing",
    "skill_selector": "tvers - velg skill for oppgaven",
}

#: Kjedens egne innganger: det som kjoerer NAAR et maal behandles.
CHAIN_ENTRYPOINTS = ("faber_runtime", "faber_control_bridge", "code_workflow")

#: SCHEDULERTE innganger. Maalt i agent@.15s crontab 2026-08-11, hver */20.
#: DE MAA MED: uten dem meldte vakten `lease_authority` som UKOBLET, mens den
#: kjoerer hvert tjuende minutt via `faber_observe`. Samme feil som
#: `.11`-crontab-blindheten i CLAUDE.md -- fravaer av LOKAL kaller beviser ikke
#: fravaer av kjoering.
SCHEDULED_ENTRYPOINTS = ("faber_observe", "faber_goal_state")

#: GATEWAY-flaten. `faber_live_adapter` naas fra `tui_gateway/methods_prompt.py`.
#: Uten denne kategorien meldte vakten `skill_selector` som doed kode mens den
#: kjoerer. TRE kategorier fordi det finnes tre svar: "ikke i kjeden" og "ikke i
#: bruk" er ulike funn med ulike neste-handlinger.
GATEWAY_MODULES = ("faber_live_adapter",)

#: Kataloger en kaller kan bo i. Kjeden spenner flere flater enn `agent/`;
#: `resolve_disagreement` sin ekte kaller laa i `hermes_cli/`.
CALLER_SURFACES = ("agent", "hermes_cli", "tui_gateway", "tools")

#: RATSJETTEN, KALIBRERT MOT HEAD -- ikke mot arbeidstreet.
#:
#: Maalt 2026-08-11:
#:     HEAD           5 ukoblet   <- taket settes her
#:     arbeidstreet   4 ukoblet   (BL-4050s steg-8-wiring ligger ukommittert)
#:
#: Jeg satte det foerst til 4, og vakten var da groenn hos meg og ROED i CI. Det
#: er noeyaktig samme feil som BL-4069 skulle rette, gjentatt ett nivaa opp: et
#: tak kalibrert mot det treet jeg tilfeldigvis sto i.
#:
#: HEAD er den konservative grensen fordi det er den ALLE ser. Et arbeidstre med
#: ukommittert wiring er en privat tilstand, og en vakt kalibrert mot en privat
#: tilstand paastaar noe om verden den bare har maalt hos seg selv.
#:
#: Tallet skal bare gaa NED. Naar BL-4050 lander, faller HEAD til 4 og taket kan
#: strammes -- det er en egen, bevisst handling.
#: BL-4070 STRAMMET 5 -> 0. Alle sju er naa naabare fra en kjede-inngang.
#:
#: Fra dette punktet er ratsjetten ikke lenger en nedtelling, men en LAAS: 0 er
#: gulvet, og enhver frakobling er nedenfra og roed. Det er den sterkeste formen
#: denne vakten kan ha, og den eneste som ikke krever vedlikehold.
#:
#: PRISEN STAAR FORTSATT, og den er viktigere naa enn foer: et tak paa 0 sier at
#: hver komponent er NAABAR, ikke at den KJOERER. En import er ikke et kall.
#: Beviset for at soemmene faktisk utfoeres bor i `tests/test_chain_seam_wiring.py`,
#: som driver hver soem og maaler at det MAALTE svaret -- ikke avsenderens --
#: er det som brukes nedstroems. De to filene svarer paa to spoersmaal som kan
#: ha ulike svar, og skal derfor ikke slaas sammen.
#:
#: OG DET ER STERKERE ENN DET: 0 LAASER IKKE FIRE SOEMMER. Reviewer viste
#: at `faber_postcommit_adapters` faar kreditt transitivt via `faber_landing`,
#: saa hele steg-12/13-wiringen kunne slettes uten at tallet roert seg. Det
#: samme gjelder `lease_authority`, som ogsaa naas fra broen. Transitiv
#: kreditt er iboende i en NAABARHETS-vakt og kan ikke fikses her. Det som
#: baerer den vekten er `tests/test_chain_seam_wiring.py`, som DRIVER hver
#: soem. Leser du 0 her, har du ikke lest at kjeden kjoerer -- du har lest at
#: ingen komponent er utilgjengelig.
MAX_UNREACHED = 0


class UnreadableModule(RuntimeError):
    """En modul kunne ikke leses. IKKE det samme som "importerer ingenting".

    Skillet er hele forskjellen mellom "komponenten er ikke koblet" og "jeg fikk
    ikke lest etter". Bare den foerste er et funn.
    """


def _agent_imports(module: str) -> set[str]:
    """Hvilke `agent.*`-moduler importerer `module`? Lest med AST, ikke regex.

    Regex paa importlinjer teller docstring-omtaler med. Det er presis feilen som
    fikk meg til aa rapportere `RuntimeSmokeGate` som kalt av `task_classifier`
    da den bare var NEVNT der.
    """
    path = REPO / "agent" / f"{module}.py"
    if not path.is_file():
        raise UnreadableModule(f"{module}: fila finnes ikke ({path})")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError) as exc:
        # FUNNET I VAKTEN SELV under mutasjonstesting: her sto ingenting, saa en
        # uleselig fil ga TOM MENGDE -- og tom mengde leses av kalleren som
        # "importerer ingenting", altsaa "ikke koblet". Vakten mot
        # fravaer-rapportert-som-funn hadde selv den formen.
        raise UnreadableModule(
            f"{module}: kunne ikke parses - {type(exc).__name__}: {exc}") from exc
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("agent."):
                out.add(node.module.split(".", 1)[1])
            elif node.module == "agent":
                # BL-4070 (reviewer BLOCK 2). `from agent import X as y` har
                # `node.module == "agent"` og navnet i `names` -- formen ble ikke
                # sett i det hele tatt. MAALT: hele steg-12/13-wiringen kunne
                # slettes uten at ratsjetten roert seg, fordi komponenten fikk
                # kreditt TRANSITIVT via `faber_landing`. En vakt som er
                # tilfreds enten ledningen finnes eller ikke, maaler ingenting --
                # noeyaktig feilklassen denne fila ble skrevet for.
                for alias in node.names:
                    out.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("agent."):
                    out.add(alias.name.split(".", 1)[1])
    return out


def _reachable_from(roots, max_depth: int = 2) -> set[str]:
    """Moduler `roots` naar, i inntil `max_depth` hopp.

    To hopp og ikke ubegrenset: en komponent som bare naas via fem mellomledd er
    ikke koblet TIL KJEDEN paa noen meningsfull maate. Grensen er en paastand om
    arkitektur, ikke en ytelsesoptimalisering.
    """
    seen: set[str] = set()
    frontier = set(roots)
    for _ in range(max_depth):
        nxt: set[str] = set()
        for mod in frontier:
            if not (REPO / "agent" / f"{mod}.py").is_file():
                continue  # foreldet konstant; fanget av egen test under
            for dep in _agent_imports(mod):
                if dep not in seen:
                    seen.add(dep)
                    nxt.add(dep)
        frontier = nxt
    return seen


def _unreached_by_chain() -> dict[str, str]:
    """Komponenter kjeden ikke naar, med hvor de ellers naas fra."""
    from_chain = _reachable_from(CHAIN_ENTRYPOINTS)
    from_cron = _reachable_from(SCHEDULED_ENTRYPOINTS)
    from_gateway = _reachable_from(GATEWAY_MODULES) | set(GATEWAY_MODULES)
    out: dict[str, str] = {}
    for module, step in sorted(CHAIN_COMPONENTS.items()):
        if module in from_chain:
            continue
        if module in from_gateway:
            out[module] = f"{step} - LIVE via gateway, kjeden spoer den ikke"
        elif module in from_cron:
            out[module] = f"{step} - LIVE via cron, kjeden spoer den ikke"
        else:
            out[module] = f"{step} - bygget, ikke koblet"
    return out


def test_every_component_exists_before_we_ask_whether_it_is_wired():
    """Rekkefoelgen er poenget: "finnes ikke" og "finnes, ukoblet" er ulike funn.

    Uten dette ville en slettet modul lest som en ukoblet én, og fiksen for de to
    er ikke den samme. Testen er umarkert med vilje, saa en sletting roper
    uavhengig av ratsjetten.
    """
    missing = [m for m in CHAIN_COMPONENTS if not (REPO / "agent" / f"{m}.py").is_file()]
    assert not missing, f"komponenter som ikke finnes: {missing}"


def test_every_named_entrypoint_actually_exists():
    """En slettet inngang ville stille krympet det vakten ser."""
    missing = [e for e in CHAIN_ENTRYPOINTS + SCHEDULED_ENTRYPOINTS + GATEWAY_MODULES
               if not (REPO / "agent" / f"{e}.py").is_file()]
    assert not missing, f"navngitte innganger som ikke finnes: {missing}"


def test_the_chain_does_not_lose_ground(capsys):
    """RATSJETTEN: antall ukoblede komponenter skal aldri oeke.

    Kartet skrives ut ved hver kjoering, fordi tallet alene ikke ville avsloert
    at én ble koblet mens en annen ble frakoblet.
    """
    unreached = _unreached_by_chain()
    with capsys.disabled():
        print("\n  KJEDENS KOBLINGSKART")
        for module, step in sorted(CHAIN_COMPONENTS.items()):
            mark = "UKOBLET" if module in unreached else "koblet " 
            print(f"    [{mark}] {module:<28} {unreached.get(module, step)}")
        print(f"    ukoblet: {len(unreached)} av {len(CHAIN_COMPONENTS)}"
              f"  (tak: {MAX_UNREACHED})")
    assert len(unreached) <= MAX_UNREACHED, (
        f"kjeden naar {len(unreached) - MAX_UNREACHED} komponent(er) faerre enn "
        f"foer. Ukoblet naa: {sorted(unreached)}. En komponent kan bare bli "
        f"ukoblet ved at noen fjernet en kobling."
    )


def test_an_unreadable_module_raises_instead_of_reading_as_unwired(tmp_path, monkeypatch):
    """Vakten maa ikke kunne forveksle "fikk ikke lest" med "ikke koblet"."""
    fake = tmp_path / "agent"
    fake.mkdir()
    (fake / "kaputt.py").write_text("def (\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    with pytest.raises(UnreadableModule) as exc:
        _agent_imports("kaputt")
    assert "kunne ikke parses" in str(exc.value)


def test_an_unreadable_module_propagates_through_the_walk(tmp_path, monkeypatch):
    """...og feilen maa BOBLE UT av traverseringen, ikke svelges der."""
    fake = tmp_path / "agent"
    fake.mkdir()
    (fake / "kaputt.py").write_text("def (\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    with pytest.raises(UnreadableModule):
        _reachable_from(("kaputt",))


def test_a_second_opinion_is_actually_requested_somewhere():
    """En andre mening som aldri BES OM er ikke en kontroll, den er en modul.

    Skanningen dekker flere flater enn `agent/`: den ekte kalleren laa i
    `hermes_cli/`, og en vakt som ser i én katalog og konkluderer om hele repoet
    melder en lukket kobling som aapen for alltid.
    """
    callers = []
    for path in sorted(q for d in CALLER_SURFACES for q in (REPO / d).rglob("*.py")):
        if path.stem == "second_opinion":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue  # fremmede filer utenfor vaart ansvar
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "agent.second_opinion":
                if any(a.name == "resolve_disagreement" for a in node.names):
                    callers.append(path.name)
    assert callers, (
        "second_opinion.resolve_disagreement har ingen kallere paa noen flate - "
        "andre-meningen er bygget, men ingen ber om den"
    )
