#!/usr/bin/env python3
"""skill_catalog_index.py — the LOCAL skill catalog, with its coverage measured (BL-4057).

## Hvorfor denne fila finnes, og hvorfor den ikke er `build_skills_index.py`

`scripts/build_skills_index.py` heter noe som får den til å se ut som svaret. Den
er det ikke, og forskjellen er ikke en detalj:

    build_skills_index.py   krabber skills.sh, ClawHub, LobeHub, GitHub-taps
                            → ~70 000 INSTALLERBARE skills fra internett
                            → `hermes skills search/install`
                            → helsegulv: skills.sh ≥ 10 000, clawhub ≥ 20 000
                            → av LOKALE kataloger leser den ÉN: optional-skills/

    denne fila             → de SKILL.md-filene som faktisk ligger på maskinen
                            → for SELEKSJON i en kjørende workflow
                            → ingen nettverk, ingen gulv, ingen GitHub-token

Den ene er en butikk-katalog. Den andre er et lager-register. Å utvide butikken til
å dekke lageret ville gitt et register som ikke kan bygges uten internett og som
nekter å skrive ut med mindre 20 000 fremmede skills svarer — for å velge blant
1026 filer som allerede ligger på disk.

## Invarianten (BL-4039, tre reviewer-runder 2026-08-10)

**Før noe rapporterer at en skill MANGLER, må det kunne si at det leste HELE
katalogen.** En halvlest katalog gjør hver referanse inn i den ulesde halvdelen
til et falskt funn.

Derfor måler denne fila dekning per rot og bærer den i indeksen:

    COMPLETE  vi kan navngi forventet omfang OG vi leste alt
    PARTIAL   vi leste noe, og vi VET det ikke er alt (målt, ikke antatt)
    UNKNOWN   vi kan ikke uttale oss om omfanget

Katalogens samlede dekning er den SVAKESTE roten. Én manglende rot smitter, fordi
en skill som mangler kan ligge nettopp der. Mønsteret er lånt fra
`tools/mwp_register_bridge.py` på .13 (`RegisterCoverage`), med vilje: det er den
samme invarianten, og den bør se lik ut begge steder.

## Målt 2026-08-11 — er de fem røttene duplikater?

Spørsmålet var berettiget (BL-4019 målte nøyaktig dette mønsteret for
opus-provideren). Svaret er **nei, de er distinkte**:

    1026 SKILL.md · 705 unike innhold · 694 unike frontmatter-navn
    (762 unike KATALOGSTIER før .archive/ trekkes fra — sti og `name:` er
     ikke samme nøkkel, og forskjellen er nettopp navnekollisjonene under)
    ~/.hermes/skills (461) vs ~/.hermes-gui/skills (287):
        94 delte navn — alle 94 med IDENTISK innhold, 0 drift
        369 kun i .hermes · 195 kun i .hermes-gui
    655 av 762 katalogstier finnes i NØYAKTIG ÉN rot

`.hermes-gui` er altså ikke et speil av `.hermes`. To trær med 94 felles navn og
564 unike er to kataloger, ikke to kopier. Å indeksere bare den ene ville tapt
195 skills.

Innholdsdrift finnes, men er liten og navngitt: `research/bioinformatics` og
`symbiose/flyby` har to innhold hver. De blir IKKE stille slått sammen — begge
beholdes, flagget `name_collision`, fordi å velge en vinner i stillhet er nøyaktig
det silent-cap-mønsteret invarianten skal hindre.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

INDEX_VERSION = 1

#: Standard utdata. Ligger under HERMES_HOME og ikke i repoet, fordi katalogen
#: beskriver MASKINEN (fem røtter, hvorav tre utenfor repoet) — ikke et commit.
DEFAULT_OUTPUT = Path(
    os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
) / "skills-catalog.json"


@dataclass(frozen=True)
class SkillRoot:
    """Én katalogrot, med navnet den rapporteres under."""

    key: str
    path: Path
    #: Lavere = høyere presedens når samme innhold finnes flere steder.
    precedence: int


def default_roots() -> tuple[SkillRoot, ...]:
    """De fem stedene skills faktisk ligger på .15 (målt 2026-08-11).

    Presedensen er rekkefølgen en leser bør stole på dem i: repoets aktive
    `skills/` er de som allerede er i systemprompten, `optional-skills/` er
    offisielle men ikke aktiverte, `~/.hermes*` er installert av brukeren, og
    MWP-repoet er prosjekt-lokalt. Presedens avgjør BARE hvilken sti som
    rapporteres som primær — alle funnsteder beholdes i `locations`.
    """
    home = Path.home()
    agent_layer = Path(os.environ.get("AGENT_LAYER", str(home / "agent-layer")))
    hermes_home = Path(os.environ.get("HERMES_HOME", str(home / ".hermes")))
    hermes_gui = Path(os.environ.get("HERMES_GUI_HOME", str(home / ".hermes-gui")))
    return (
        SkillRoot("repo_active", agent_layer / "hermes-agent" / "skills", 0),
        SkillRoot("repo_optional", agent_layer / "hermes-agent" / "optional-skills", 1),
        SkillRoot("hermes_home", hermes_home / "skills", 2),
        SkillRoot("hermes_gui", hermes_gui / "skills", 3),
        SkillRoot("mwp", agent_layer / "mwp-uosh-automation-01" / "skills", 4),
    )


class Coverage(str, Enum):
    """Kan vi si at vi leste HELE denne roten?

    Se modul-docstringen. `read_errors: []` betyr bare at ingenting feilet —
    ikke at noe var fullstendig.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


#: Svakeste-ledd-rekkefølge. En katalog er ikke sterkere enn sin dårligste rot.
_COVERAGE_RANK = {Coverage.COMPLETE: 0, Coverage.PARTIAL: 1, Coverage.UNKNOWN: 2}


def weakest(states: Iterable[Coverage]) -> Coverage:
    """Samlet dekning = den svakeste roten.

    Tom sekvens gir UNKNOWN, ikke COMPLETE: å ikke ha lest noen røtter er det
    motsatte av å ha lest alt. Dette er fella `all([])  is True` legger ut, og
    den ville gjort en tom katalog til den mest selvsikre.
    """
    materialised = list(states)
    if not materialised:
        return Coverage.UNKNOWN
    return max(materialised, key=lambda s: _COVERAGE_RANK[s])


@dataclass(frozen=True)
class RootCoverage:
    """Dekningen for ÉN rot, med beviset."""

    key: str
    source: str
    state: Coverage
    read: int
    expected: int | None
    note: str = ""
    errors: tuple[str, ...] = ()
    #: Lenkemål utenfor roten som BLE fulgt. Provenans, ikke degradering:
    #: dekningen er fortsatt sann, men leseren skal kunne se hva som ble tatt med
    #: og hvorfra. `scope_narrowed` sier «jeg så på mindre enn maskinen»; dette
    #: sier «jeg så på mer enn roten», og det fantes ikke noe felt for det.
    out_of_root: tuple[str, ...] = ()
    #: Forelder-lenker vi nektet å følge. En OMFANGSBESLUTNING, ikke en
    #: dekningspåstand — se scan_root(). De kan bære skills vi da ikke leser.
    refused_links: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.state is Coverage.COMPLETE

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "source": self.source,
            "state": self.state.value,
            "read": self.read,
            "expected": self.expected,
            "note": self.note,
            "errors": list(self.errors),
            "out_of_root": list(self.out_of_root),
            "refused_links": list(self.refused_links),
            "is_complete": self.is_complete,
        }


#: Hvor mye av SKILL.md-BRØDTEKSTEN som indekseres, i tegn.
#:
#: Målt 2026-08-11: frontmatter-beskrivelsene er énlinjere — median 17 tokens.
#: Så tynt at `df["cypher"] == 0` over hele katalogen, mens `df["returns"] == 1`
#: (fra en nettbutikk-skills «returns»-policy). Et enkelt-treff på et sjeldent,
#: tilfeldig ord slo dermed det topiske ordet, fordi IDF ikke kan skille
#: «sjelden» fra «relevant» når det ikke finnes mer tekst å gå på.
#:
#: Brødteksten er der signalet faktisk ligger. Grensen holder indeksen rundt
#: 2 MB for 705 skills og er et bevisst tak — ikke et stille kutt: den
#: rapporteres i indeksen som `body_chars`.
BODY_INDEX_CHARS = 3000


@dataclass
class SkillEntry:
    """Én skill, med ALLE stedene den ble funnet."""

    name: str
    description: str
    content_md5: str
    primary_path: str
    primary_root: str
    #: Bundet utdrag av brødteksten. Se BODY_INDEX_CHARS.
    body: str = ""
    #: Andre navn samme innhold ble funnet under. Se merge().
    aliases: list[str] = field(default_factory=list)
    locations: list[dict[str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    archived: bool = False
    #: True når et annet innhold deler dette navnet. Se modul-docstringen —
    #: kolliderende navn slås ikke sammen i stillhet.
    name_collision: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "content_md5": self.content_md5,
            "primary_path": self.primary_path,
            "primary_root": self.primary_root,
            "body": self.body,
            "aliases": self.aliases,
            "locations": self.locations,
            "tags": self.tags,
            "archived": self.archived,
            "name_collision": self.name_collision,
        }


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Les YAML-frontmatter fra en SKILL.md.

    Returnerer {} når fila ikke har frontmatter. Kaster ved ØDELAGT frontmatter
    — en fil som åpner med `---` og ikke lar seg parse er en LESEFEIL, ikke en
    fil uten metadata, og den skal telles som sådan (ellers blir PARTIAL til
    COMPLETE ved at feilen forsvinner inn i en tom dict).
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("frontmatter opened with --- but never closed")
    block = text[3:end]
    import yaml

    loaded = yaml.safe_load(block)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"frontmatter is {type(loaded).__name__}, expected mapping")
    return loaded


def body_excerpt(text: str, limit: int = BODY_INDEX_CHARS) -> str:
    """Brødteksten etter frontmatter, normalisert og bundet.

    Kodeblokker beholdes: en skill som nevner `MATCH (n:Label)` bærer nettopp
    der ordene som skiller den fra naboen. Whitespace kollapses slik at
    dokumentlengden måler innhold og ikke formatering — BM25 normaliserer på
    lengde, og ellers ville en skill med luftig markdown fremstått som lengre
    enn en tettskrevet med samme innhold.
    """
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4 :]
    return " ".join(body.split())[:limit]


def _as_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, (list, tuple)):
        return [str(t).strip() for t in value if str(t).strip()]
    return []


def scan_root(root: SkillRoot, *, include_archive: bool = False) -> tuple[RootCoverage, list[SkillEntry]]:
    """Skann én rot og MÅL dekningen.

    To faser med vilje: først telle opp (`expected`), så lese (`read`). Å telle
    de leste filene som fasit ville gjort enhver fil som ikke lot seg åpne
    usynlig — og dermed gjort dekningen selvbekreftende.
    """
    if not root.path.is_dir():
        return (
            RootCoverage(root.key, str(root.path), Coverage.UNKNOWN, 0, None,
                         "roten finnes ikke — omfanget er ukjent, ikke null"),
            [],
        )

    # os.walk med onerror — IKKE rglob.
    #
    # Reviewer 2026-08-11 (BL-4057 runde 1) felte den forrige versjonen her:
    # `expected = len(root.path.rglob(...))` teller de samme filene som leses,
    # og pathlib SVELGER OSError mens den traverserer. En katalog med mode 000
    # ble dermed usynlig for BEGGE tellerne — roten rapporterte COMPLETE med
    # `errors: ()` mens en skill lå ulest inni. Det er invarianten beseiret ved
    # roten: en `MISSING`-påstand kunne utstedes mot en skill som fantes.
    #
    # `expected` er fortsatt ikke en uavhengig kilde — men nå kan traverseringen
    # ikke lenger feile i stillhet, og en utilgjengelig undermappe blir en
    # LESEFEIL som senker roten til PARTIAL.
    walk_errors: list[str] = []

    def _on_error(exc: OSError) -> None:
        walk_errors.append(f"{getattr(exc, 'filename', '?')}: {type(exc).__name__}: {exc}")

    # followlinks=True — med syklusvern.
    #
    # Reviewer 2026-08-11 runde 2 fant den siste formen av samme blindsone:
    # `os.walk(followlinks=False)` hopper over en SYMLENKET undermappe uten at
    # det telles som lesefeil. `read == expected`, `errors: ()`, COMPLETE — og
    # skillen bak lenken er simpelthen borte. Nøyaktig samme form som
    # permission-bit-hullet, med en symlenke i stedet.
    #
    # Å telle den som et HULL (→ PARTIAL) ville vært feil medisin: den som med
    # vilje symlenker en skill-katalog ville låst katalogen til PARTIAL for
    # alltid, og dermed gjort MISSING uoppnåelig — samme avbryter-form som
    # manglende bygger var. Riktig svar er å FØLGE lenken, slik at skillen
    # faktisk blir lest og COMPLETE fortsatt er sant.
    #
    # Prisen for followlinks er sykler (a/b -> a). `seen` holder realpath for
    # hver besøkt katalog; en katalog vi allerede har vært i, traverseres ikke
    # om igjen. Uten det henger byggeren for alltid på en enkelt lenke.
    found: list[Path] = []
    seen: set[str] = set()
    root_real = os.path.realpath(root.path)
    # Lenker som peker UT av roten. Ikke en degradering — se build_index().
    outside: set[str] = set()
    # Lenker vi nektet å følge fordi de peker på en FORELDER av roten.
    refused: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root.path, onerror=_on_error,
                                                followlinks=True):
        real = os.path.realpath(dirpath)
        if real in seen:
            # Syklus eller delt undertre — allerede lest, ikke et hull.
            dirnames[:] = []
            continue
        seen.add(real)

        # Forelder-lenke = katalog-krasj. `ln -s / root/x` gjør den timesvis
        # cronen til en filsystem-traversering. Målt av reviewer 2026-08-11: ÉN
        # uhells-lenke inn i repoet dro 203 skills inn i en rot med 1.
        #
        # HVORFOR DETTE KAN NEKTES UTEN Å SENKE DEKNINGEN — og det er IKKE fordi
        # «roten dekker dem». Det sto her først, og det er usant: en forelder
        # inneholder roten, men den inneholder også alt VED SIDEN AV roten.
        # Reviewer felte formuleringen med et motbevis (tre søsken-skills nådd
        # fra innsiden av roten, ikke lest). I en endring som handler om
        # påstander som løper foran beviset sitt, er en kommentar som lover mer
        # enn koden holder nettopp den defekten som ikke får lov å gå gjennom.
        #
        # Den ekte grunnen: det DEKLARERTE omfanget er de fem røttene. En
        # forelder-lenke ville utvidet omfanget forbi roten i stillhet. Å nekte
        # er derfor en OMFANGSBESLUTNING som noteres — ikke en dekningspåstand.
        # Regelen bak: et MÅLEHULL senker dekningen; en POLICY-UTELUKKELSE
        # noteres og senker den ikke.
        kept = []
        for name in dirnames:
            child = os.path.join(dirpath, name)
            if not os.path.islink(child):
                kept.append(name)
                continue
            target = os.path.realpath(child)
            if root_real == target or root_real.startswith(target.rstrip(os.sep) + os.sep):
                refused.add(target)
                continue
            if target != root_real and not target.startswith(root_real.rstrip(os.sep) + os.sep):
                outside.add(target)
            kept.append(name)
        dirnames[:] = kept

        if "SKILL.md" in filenames:
            skill_file = Path(dirpath) / "SKILL.md"
            # os.walk eksponerer bare KATALOGERS lenke-status via dirnames.
            # Reviewer 2026-08-11: `root/sneak/SKILL.md -> /andre/sted/SKILL.md`
            # ble lest, indeksert under en kanonisk rot-nøkkel, og var
            # valgbar for systemprompten — mens out_of_root rapporterte
            # ingenting. Et provenansfelt som ikke dekker alle veier inn er
            # verre enn ingen: det blir trodd.
            if os.path.islink(skill_file):
                target = os.path.realpath(skill_file)
                if not target.startswith(root_real.rstrip(os.sep) + os.sep):
                    outside.add(target)
            found.append(skill_file)
    found.sort()

    expected = len(found)
    entries: list[SkillEntry] = []
    errors: list[str] = list(walk_errors)
    archived_skipped = 0

    for path in found:
        rel = path.relative_to(root.path)
        skill_name = str(rel.parent).replace(os.sep, "/")
        is_archived = skill_name.startswith(".archive/") or "/.archive/" in f"/{skill_name}"
        if is_archived and not include_archive:
            archived_skipped += 1
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: {type(exc).__name__}: {exc}")
            continue
        try:
            meta = parse_frontmatter(text)
        except Exception as exc:  # noqa: BLE001 — enhver parsefeil er en lesefeil
            errors.append(f"{rel}: frontmatter: {type(exc).__name__}: {exc}")
            continue

        name = str(meta.get("name") or skill_name).strip() or skill_name
        description = " ".join(str(meta.get("description") or "").split())
        entries.append(
            SkillEntry(
                name=name,
                description=description,
                content_md5=hashlib.md5(text.encode("utf-8")).hexdigest(),
                primary_path=str(path),
                primary_root=root.key,
                body=body_excerpt(text),
                locations=[{"root": root.key, "path": str(path)}],
                tags=_as_tags(meta.get("tags")),
                archived=is_archived,
            )
        )

    # `read` teller filer vi FAKTISK håndterte. Bevisst hoppede arkiv-filer er
    # håndtert, ikke tapt — de rapporteres i noten, ikke som et hull. Det er
    # forskjellen på et målt valg og et stille kutt.
    read = len(entries) + archived_skipped
    note_bits = []
    if archived_skipped:
        note_bits.append(f"{archived_skipped} .archive/-skills bevisst utelatt (--include-archive tar dem med)")

    if errors:
        note_bits.append(f"{len(errors)} filer kunne ikke leses")
        return (
            RootCoverage(root.key, str(root.path), Coverage.PARTIAL, read, expected,
                         "; ".join(note_bits), tuple(errors[:20]),
                         tuple(sorted(outside)), tuple(sorted(refused))),
            entries,
        )

    if read != expected:
        note_bits.append(f"leste {read} av {expected} — differansen er UAVKLART")
        return (
            RootCoverage(root.key, str(root.path), Coverage.PARTIAL, read, expected,
                         "; ".join(note_bits), (),
                         tuple(sorted(outside)), tuple(sorted(refused))),
            entries,
        )

    note_bits.append(f"alle {expected} SKILL.md lest")
    if outside:
        note_bits.append(f"{len(outside)} lenkemål UTENFOR roten ble fulgt og tatt med")
    if refused:
        note_bits.append(f"{len(refused)} forelder-lenke(r) ikke fulgt — ville utvidet "
                         f"omfanget forbi roten; målet er notert")
    return (
        RootCoverage(root.key, str(root.path), Coverage.COMPLETE, read, expected,
                     "; ".join(note_bits), (),
                     tuple(sorted(outside)), tuple(sorted(refused))),
        entries,
    )


def merge(entries: Sequence[SkillEntry], roots: Sequence[SkillRoot]) -> list[SkillEntry]:
    """Slå sammen på INNHOLD, ikke på navn.

    Samme innhold flere steder er én skill funnet flere ganger — locations
    vokser. Samme navn med ULIKT innhold er to skills som deler navn: begge
    beholdes og begge flagges `name_collision`. Å la den ene vinne i stillhet
    ville skjult nettopp den driften BL-4019 lærte oss å måle.
    """
    order = {r.key: r.precedence for r in roots}
    by_content: dict[str, SkillEntry] = {}
    for entry in entries:
        existing = by_content.get(entry.content_md5)
        if existing is None:
            by_content[entry.content_md5] = entry
            continue
        existing.locations.extend(entry.locations)
        # Et navn som taper presedens-kampen skal fortsatt være FINNBART.
        #
        # Reviewer 2026-08-11 (latent): to bytelike filer uten `name:` i
        # frontmatter arver hver sin katalognavn (`alpha-tool`, `beta-tool`),
        # men md5-dedupen beholder bare det ene — og det andre navnet forsvant
        # uten at `name_collision` ble satt. Ikke levende i dag (alle 1026
        # filer har `name:`), men det er en stille sletting, og de er verdt å
        # lukke før de blir levende.
        if entry.name != existing.name and entry.name not in existing.aliases:
            existing.aliases.append(entry.name)
        if order.get(entry.primary_root, 99) < order.get(existing.primary_root, 99):
            if existing.name != entry.name and existing.name not in existing.aliases:
                existing.aliases.append(existing.name)
            existing.primary_path = entry.primary_path
            existing.primary_root = entry.primary_root
            existing.name = entry.name
            existing.description = entry.description
            existing.tags = entry.tags
            existing.body = entry.body

    merged = list(by_content.values())
    by_name: dict[str, list[SkillEntry]] = {}
    for entry in merged:
        by_name.setdefault(entry.name, []).append(entry)
    for name, group in by_name.items():
        if len(group) > 1:
            for entry in group:
                entry.name_collision = True

    merged.sort(key=lambda e: (order.get(e.primary_root, 99), e.name))
    return merged


def build_index(
    roots: Sequence[SkillRoot] | None = None,
    *,
    include_archive: bool = False,
) -> dict[str, Any]:
    """Bygg katalogen og bær dekningen med den."""
    roots = tuple(roots if roots is not None else default_roots())
    coverages: list[RootCoverage] = []
    all_entries: list[SkillEntry] = []
    for root in roots:
        coverage, entries = scan_root(root, include_archive=include_archive)
        coverages.append(coverage)
        all_entries.extend(entries)

    merged = merge(all_entries, roots)
    catalog_state = weakest(c.state for c in coverages)

    # DYBDE er målt over; OMFANG måles her.
    #
    # Reviewer 2026-08-11: `build_index([repo_active])` ga `catalog_coverage:
    # complete` med 81 skills mens 624 lå i de fire andre røttene — og prompten
    # sa «from 81 indexed, catalog coverage COMPLETE». Å ha lest ALT av det man
    # valgte å se på, er ikke å ha lest alt. En innsnevret rot-liste (via --root
    # eller via AGENT_LAYER/HERMES_HOME/HERMES_GUI_HOME) er nettopp den
    # halvleste katalogen invarianten handler om, bare med hullet flyttet fra
    # lesingen til utvalget.
    scanned = {r.key for r in roots}
    canonical = {r.key for r in default_roots()}
    missing_roots = sorted(canonical - scanned)

    # To rot-NØKLER som peker på samme KATALOG er ikke to røtter.
    #
    # Målt 2026-08-11: under `HERMES_HOME=/home/agent/.hermes-gui` — som den
    # eksisterende faber-cronen faktisk bruker — løser både `hermes_home` og
    # `hermes_gui` til `~/.hermes-gui/skills`. Da blir `~/.hermes/skills` (461
    # skills) ALDRI skannet, mens rot-lista fortsatt har fem nøkler og
    # katalogen ville meldt COMPLETE. Samme omfangsfeil som `scope_narrowed`
    # fanger, men forkledd som full dekning i stedet for som en kort liste.
    by_path: dict[str, list[str]] = {}
    for r in roots:
        try:
            resolved = str(r.path.resolve())
        except OSError:
            resolved = str(r.path)
        by_path.setdefault(resolved, []).append(r.key)
    collisions = sorted(
        ({"path": p, "keys": sorted(keys)} for p, keys in by_path.items() if len(keys) > 1),
        key=lambda c: c["path"],
    )

    # Nøstede røtter: én rot som ligger INNI en annen.
    #
    # Ikke levende på .15 (målt: ingen av de fem er nøstet eller symlenket), og
    # bevisst behandlet mildere enn en kollisjon: en nøstet rot fører til at de
    # samme filene leses to ganger, ikke til at noen blir uleste — og merge()
    # slår dem sammen på innhold, så resultatet er riktig. Den LYVER altså ikke
    # om dekning; den blåser opp `files_seen`. Derfor rapporteres den uten å
    # degradere. En symlenke som peker på en annen rot fanges allerede av
    # kollisjonssjekken over, siden begge løser til samme sti.
    nested: list[dict[str, str]] = []
    _resolved = [(r.key, str(r.path.resolve()) if r.path.exists() else str(r.path))
                 for r in roots]
    for a_key, a_path in _resolved:
        for b_key, b_path in _resolved:
            if a_key != b_key and a_path.startswith(b_path.rstrip(os.sep) + os.sep):
                nested.append({"inner": a_key, "outer": b_key, "path": a_path})

    if (missing_roots or collisions) and catalog_state is Coverage.COMPLETE:
        catalog_state = Coverage.PARTIAL

    return {
        "version": INDEX_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "include_archive": include_archive,
        # Taket rapporteres, ikke antas: en leser skal kunne se at brødteksten
        # er avkortet og hvor.
        "body_chars": BODY_INDEX_CHARS,
        # Samlet dekning er den SVAKESTE roten — se weakest().
        "catalog_coverage": catalog_state.value,
        "catalog_coverage_complete": catalog_state is Coverage.COMPLETE,
        # Omfanget, skrevet ned så en leser kan se HVA som ble sett på — ikke
        # bare hvor godt det ble lest.
        "roots_scanned": sorted(scanned),
        "roots_canonical": sorted(canonical),
        "roots_missing": missing_roots,
        "root_path_collisions": collisions,
        "root_nesting": nested,
        # Motstykket til scope_narrowed. Degraderer IKKE — dekningen er sann,
        # dette forteller bare hvor innholdet kom fra.
        "out_of_root_targets": sorted({t for c in coverages for t in c.out_of_root}),
        "scope_widened": any(c.out_of_root for c in coverages),
        "refused_parent_links": sorted({t for c in coverages for t in c.refused_links}),
        "scope_narrowed": bool(missing_roots or collisions),
        "roots": [c.to_json() for c in coverages],
        "files_seen": sum(c.read for c in coverages),
        "skill_count": len(merged),
        "name_collisions": sorted({e.name for e in merged if e.name_collision}),
        "skills": [e.to_json() for e in merged],
    }


def write_index(index: dict[str, Any], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the LOCAL skill catalog index (BL-4057)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--include-archive", action="store_true",
                    help="ta med .archive/-skills (utelatt som standard, alltid rapportert)")
    ap.add_argument("--root", action="append", default=[], metavar="KEY=PATH",
                    help="overstyr/legg til en rot (kan gjentas)")
    ap.add_argument("--json", action="store_true", help="skriv indeksen til stdout i stedet for fil")
    args = ap.parse_args(argv)

    roots = list(default_roots())
    for spec in args.root:
        key, _, raw = spec.partition("=")
        if not raw:
            print(f"--root krever KEY=PATH, fikk: {spec}", file=sys.stderr)
            return 2
        roots = [r for r in roots if r.key != key]
        roots.append(SkillRoot(key, Path(raw).expanduser(), len(roots)))

    index = build_index(roots, include_archive=args.include_archive)

    if args.json:
        json.dump(index, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")
    else:
        path = write_index(index, args.out)
        print(f"skrev {index['skill_count']} skills → {path}")

    for root in index["roots"]:
        mark = "OK  " if root["is_complete"] else "!!  "
        exp = root["expected"] if root["expected"] is not None else "?"
        print(f"  {mark}{root['key']:<14} {root['state']:<8} {root['read']}/{exp}  {root['note']}",
              file=sys.stderr)
    print(f"  katalog-dekning: {index['catalog_coverage'].upper()}"
          f" — {index['skill_count']} unike skills av {index['files_seen']} filer",
          file=sys.stderr)
    if index["scope_widened"]:
        for t in index["out_of_root_targets"]:
            print(f"  ??  lenkemål utenfor roten ble tatt med: {t}", file=sys.stderr)
    for t in index["refused_parent_links"]:
        print(f"  --  forelder-lenke ikke fulgt (roten dekker den): {t}", file=sys.stderr)
    if index["root_path_collisions"]:
        for c in index["root_path_collisions"]:
            print(f"  !!  rot-kollisjon: {'+'.join(c['keys'])} peker begge på {c['path']}",
                  file=sys.stderr)
    if index["name_collisions"]:
        print(f"  navnekollisjoner (begge beholdt): {', '.join(index['name_collisions'])}",
              file=sys.stderr)

    # Exit 1 ved ufullstendig dekning: en katalog som ikke vet sitt eget omfang
    # skal ikke passere en CI-gate i stillhet. Fila skrives likevel — en PARTIAL
    # katalog er brukbar for SELEKSJON, den er bare ikke brukbar for å påstå at
    # noe MANGLER, og selektoren håndhever nettopp det skillet.
    return 0 if index["catalog_coverage_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
