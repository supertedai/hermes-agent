"""skill_selector.py — skill-seleksjon som en MEKANISME, ikke en påstand (BL-4057).

## Hva som manglet

Koblingen mellom 1026 SKILL.md og den 13-stegs kode-workflowen var ÉN setning i
én systemprompt:

    agent/faber_live_adapter.py:16
    "Use your own faber.codex memory and skills."

Det er en påstand om at modellen husker at den har skills. Grep på
`select_skill` / `choose_skill` / `match_skill` / `relevant_skill` ga null treff i
hele repoet. 1026 skills, ingen velger.

Forskjellen på denne modulen og setningen over: denne kan man MÅLE. `select()`
returnerer hvilke skills som ble vurdert, hvilke som vant, med hvilken score, og
under hvilken dekning — og skriver det til et spor. En seleksjon ingen kan
observere er ikke koblet.

## Invarianten (BL-4039)

**Før noe rapporterer at en skill MANGLER, må det kunne si at det leste HELE
katalogen.**

Den er håndhevet strukturelt her, ikke som en konvensjon: `SkillSelection` bærer
dekningen fra indeksen, og `report_missing()` NEKTER å svare «mangler» med mindre
dekningen er COMPLETE. Under PARTIAL/UNKNOWN er svaret `UNRESOLVED` — som er noe
annet enn «finnes ikke», og som ikke kan forveksles med det ved et uhell.

Grunnen dette er strukturelt og ikke en husregel: en halvlest katalog gjør hver
referanse inn i den ulesde halvdelen til et FALSKT FUNN, og et falskt funn ser
akkurat ut som et ekte til noen sjekker. Tre reviewer-runder 2026-08-10 fikset
hver sin instans før invarianten fikk navn.

## Scoring

BM25 over `name` (×3) + `description` (×2) + `tags` + BRØDTEKST, ganget med hvor
stor andel av spørringens termer som traff. Bevisst deterministisk og lokal:
ingen embeddings, ingen nettverkskall. Et steg i en kode-workflow må kunne kjøre
seleksjonen synkront, reprodusere den i en test, og forklare den i et spor. En
vektor-DB ville gitt bedre recall og dårligere av alle tre.

At brødteksten er med er ikke en detalj. Målt 2026-08-11 med bare frontmatter —
median 17 tokens per skill — valgte oppgaven «neo4j cypher query returns stale
rows» skillen `shop`, på ett treff: «returns», fra en returordning. `cypher`
fantes ikke i en eneste beskrivelse i hele katalogen. Med brødtekst og
dekningsvekt treffer samme oppgave `symbiose-runtime-integration-verification`
på fem termer. Se `_bm25` og `skill_catalog_index.BODY_INDEX_CHARS`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def default_index_path() -> Path:
    """Hvor katalogen ligger — løst ved KALL, ikke ved import.

    Samme sti som `skill_catalog_index.DEFAULT_OUTPUT`, men duplisert bevisst:
    denne modulen importeres av agent-runtime og skal ikke dra inn byggeren (og
    dens yaml-avhengighet) bare for å lese en JSON-fil.

    Import-tidspunktet var feil sted å fryse stien. En modul som importeres én
    gang per prosess ville låst seg til miljøet slik det så ut da noe helt annet
    tilfeldigvis importerte den først — som gjør både test-isolasjon og
    per-profil HERMES_HOME til flaks.
    """
    override = os.environ.get("HERMES_SKILL_INDEX", "").strip()
    return Path(override) if override else _hermes_home() / "skills-catalog.json"


def default_trace_path() -> Path:
    override = os.environ.get("HERMES_SKILL_TRACE", "").strip()
    return Path(override) if override else _hermes_home() / "skill-selection-trace.jsonl"


#: Hvor lenge en indeks får påstå COMPLETE før alderen alene degraderer den.
#:
#: Dekning er en MÅLING, og en måling har et tidspunkt. En indeks bygget én gang
#: og aldri siden ville fortsatt si COMPLETE mens noen installerte femti nye
#: skills — og da er «vi leste hele katalogen» ikke lenger sant, uten at noe
#: feilet. Det er den samme invarianten (BL-4039) anvendt på tid: en påstand om
#: fullstendighet forfaller når grunnlaget for den blir gammelt.
#:
#: Degraderingen går til PARTIAL, ikke UNKNOWN: vi leste faktisk noe, og vi vet
#: at det kanskje ikke er alt lenger. Det er nøyaktig definisjonen av PARTIAL.
def _int_env(name: str, default: int) -> int:
    """Les en heltalls-env uten å kunne felle importen.

    Reviewer 2026-08-11: `int(os.environ[...])` på modulnivå kaster ValueError
    ved en skrivefeil i miljøet — og tar med seg importen av den GOVERNEDE
    adapteren i fallet. En miljøvariabel skal kunne være feil uten at en
    kode-review-sti forsvinner.
    """
    try:
        return int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


MAX_INDEX_AGE_S = _int_env("HERMES_SKILL_INDEX_MAX_AGE_S", 24 * 3600)

_TOKEN = re.compile(r"[a-z0-9]+")

#: Ord som finnes i nesten enhver kodeoppgave og derfor ikke skiller skills fra
#: hverandre. Holdt kort med vilje — IDF nedvekter resten av seg selv.
_STOP = frozenset("""
a an the and or of to in on for with without is are be by from as at it its this that
use uses using used how what when where which who why do does did make makes made
skill skills task tasks work working
after before but not no so then than there here they we you my our their your
all any some new old still just only also more most less into if else while during
was were been has have had can could should would will shall may might must
en et og eller av til i på med uten er som den det de har hva hvordan når hvor
bruk bruke brukes gjør gjøre lag lage etter før men ikke ingen så enn der
alle noen ny gammel bare kun også mer mest mindre hvis ellers mens under
var vare blitt kan kunne skal skulle ville må
""".split())


def _text(value: Any) -> str:
    """Tving en indeksverdi til tekst uten å kunne kaste.

    Reviewer 2026-08-11 runde 2: formvalideringen i `load()` er på TOPPNIVÅ —
    den fanger `skills` som ikke er dicts, men ikke `name: 123`, `tags: [1,2]`
    eller `body: {...}`. De kastet fortsatt AttributeError/TypeError inne i
    indekseringen. Adapteren fanger det, men `select_for_task` og CLI-en gjorde
    det ikke. En indeksfil er data utenfra; den skal ikke kunne felle en kaller
    ved å ha feil type i et felt.
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_text(v) for v in value)
    return str(value)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


@dataclass(frozen=True)
class ScoredSkill:
    """Én skill med scoren sin — og hvorfor den fikk den."""

    name: str
    score: float
    primary_path: str
    primary_root: str
    description: str
    #: Hvilke spørringstermer som faktisk traff. Dette er forskjellen på en
    #: score man kan ettergå og et tall.
    matched_terms: tuple[str, ...]
    name_collision: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "primary_path": self.primary_path,
            "primary_root": self.primary_root,
            "matched_terms": list(self.matched_terms),
            "name_collision": self.name_collision,
        }


@dataclass(frozen=True)
class SkillSelection:
    """Resultatet av ett seleksjonskall — inkludert hva vi IKKE kan påstå.

    `coverage` er arvet fra indeksen og er grunnen til at dette er en dataklasse
    og ikke en liste: en liste over treff kan ikke bære «og forresten, vi leste
    bare halve katalogen».
    """

    query: str
    coverage: str
    considered: int
    selected: tuple[ScoredSkill, ...]
    #: Hvor mange brukbare termer spørringen faktisk ga. Null betyr at vi ikke
    #: spurte om noe — se `queryable` og report_missing().
    query_terms: int = 0
    index_generated_at: str = ""
    index_path: str = ""
    note: str = ""

    @property
    def coverage_complete(self) -> bool:
        return self.coverage == "complete"

    @property
    def queryable(self) -> bool:
        """Stilte vi i det hele tatt et spørsmål katalogen kunne svare på?

        Reviewer 2026-08-11: en tur med bare tegnsetting («{ } ; ++ >>>»), bare
        stoppord, eller bare CJK ga null termer — og fikk svaret «katalogen ble
        lest i sin helhet, dette er et MÅLT fravær». Fraværet var av SPØRRING,
        ikke av katalog. Full dekning gjør ikke et ikke-stilt spørsmål besvart.
        """
        return self.query_terms > 0

    @property
    def top(self) -> ScoredSkill | None:
        return self.selected[0] if self.selected else None

    def to_json(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage,
            "coverage_complete": self.coverage_complete,
            "queryable": self.queryable,
            "query_terms": self.query_terms,
            "considered": self.considered,
            "selected": [s.to_json() for s in self.selected],
            "index_generated_at": self.index_generated_at,
            "index_path": self.index_path,
            "note": self.note,
        }


class SkillCatalog:
    """Den lokale katalogen, lest én gang og spurt mange ganger."""

    def __init__(self, index: dict[str, Any], *, index_path: str = ""):
        self._index = index
        self._index_path = index_path
        self._skills: list[dict[str, Any]] = list(index.get("skills") or [])
        self._docs: list[list[str]] = []
        self._df: dict[str, int] = {}
        for skill in self._skills:
            # Navnet vektes ×3 ved å telles tre ganger — enklere og mer
            # gjennomsiktig i sporet enn en egen feltvekt i scoringen.
            # Brødteksten teller én gang: den bærer det meste av signalet
            # (beskrivelsene er énlinjere), men skal ikke drukne navnet.
            raw_name = _text(skill.get("name")).replace("/", " ").replace("-", " ")
            # Aliaser teller som navn. Reviewer 2026-08-11 runde 2 gjenåpnet
            # dette: indekseren SKREV aliases, selektoren leste dem aldri, så et
            # navn som tapte md5-dedupen fikk «measured absence» — navnet lå på
            # disk, i indeksen, og ble likevel meldt fraværende. Å skrive et felt
            # ingen leser er ikke å lukke hullet, det er å dokumentere det.
            alias_names = " ".join(_text(a).replace("/", " ").replace("-", " ")
                                   for a in (skill.get("aliases") or []))
            doc = (
                _tokens(raw_name) * 3
                + _tokens(alias_names) * 3
                + _tokens(_text(skill.get("description"))) * 2
                + _tokens(" ".join(_text(t) for t in (skill.get("tags") or [])))
                + _tokens(_text(skill.get("body")))
            )
            self._docs.append(doc)
            for term in set(doc):
                self._df[term] = self._df.get(term, 0) + 1
        self._avg_len = (sum(len(d) for d in self._docs) / len(self._docs)) if self._docs else 0.0

    # -- konstruksjon ---------------------------------------------------

    @classmethod
    def load(cls, path: Path | str | None = None) -> "SkillCatalog":
        """Les indeksen fra disk.

        En manglende indeks er IKKE en tom katalog. Den blir en katalog med
        dekning UNKNOWN — som betyr at ingenting kan kalles manglende. Å
        returnere en tom liste her ville gjort «indeksen er ikke bygget» til
        «det finnes ingen skills», og det er nøyaktig det falske funnet
        invarianten skal hindre.
        """
        p = Path(path) if path is not None else default_index_path()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("index is not an object")
            skills = raw.get("skills")
            if skills is not None and (
                not isinstance(skills, list)
                or not all(isinstance(s, dict) for s in skills)
            ):
                # Formfeil MÅ fanges her, ikke i __init__. Reviewer 2026-08-11:
                # en `skills`-liste med noe annet enn dicts ga AttributeError
                # inne i indekseringen — som slapp ut av den governede stien og
                # etterlot goal_id i _ACTIVE for alltid.
                raise ValueError("index.skills is not a list of objects")
        except Exception as exc:  # noqa: BLE001 — enhver lesefeil er UNKNOWN, ikke tom
            return cls(
                {
                    "catalog_coverage": "unknown",
                    "skills": [],
                    "generated_at": "",
                    "_load_error": f"{type(exc).__name__}: {exc}",
                },
                index_path=str(p),
            )
        return cls(raw, index_path=str(p))

    # -- egenskaper -----------------------------------------------------

    @property
    def coverage(self) -> str:
        """Dekningen slik den gjelder NÅ — ikke slik den var da indeksen ble bygget.

        En gammel indeks får ikke beholde COMPLETE. Se MAX_INDEX_AGE_S.
        """
        declared = str(self._index.get("catalog_coverage") or "unknown")
        if declared != "complete":
            return declared
        # Billig belte: byggeren degraderer allerede selv ved innsnevret omfang,
        # men selektoren skal ikke være avhengig av at den eneste skriveren
        # oppfører seg. Et COMPLETE med scope_narrowed satt er selvmotsigende.
        if self._index.get("scope_narrowed") or self._index.get("roots_missing"):
            return "partial"
        # Reviewer 2026-08-11: en indeks UTEN lesbart tidsstempel beholdt
        # COMPLETE for alltid — foreldelsesregelen kunne omgås ved å fjerne
        # beviset for alder. En påstand om ferskhet man ikke kan etterprøve er
        # ikke en fersk påstand.
        age = self.age_seconds
        if age is None or not (0 <= age <= MAX_INDEX_AGE_S):
            return "partial"
        return declared

    @property
    def age_seconds(self) -> float | None:
        """Indeksens alder, eller None hvis tidsstempelet ikke kan leses."""
        stamp = str(self._index.get("generated_at") or "")
        if not stamp:
            return None
        try:
            built = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if built.tzinfo is None:
            built = built.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - built).total_seconds()

    @property
    def is_stale(self) -> bool:
        """Kan vi IKKE gå god for at indeksen er fersk?

        Umålbar alder teller som foreldet. Navnet er valgt for å svare på det
        spørsmålet og ikke på «er den beviselig gammel», fordi det var den
        forrige formuleringen som lot et manglende tidsstempel passere.
        """
        age = self.age_seconds
        # Negativ alder = fremtidsdatert stempel. Reviewer 2026-08-11 runde 2:
        # `age_h: -87600` ga `is_stale: False` og full tillit. En klokke som
        # peker feil vei er ikke et ferskhetsbevis.
        return age is None or not (0 <= age <= MAX_INDEX_AGE_S)

    @property
    def coverage_complete(self) -> bool:
        return self.coverage == "complete"

    @property
    def size(self) -> int:
        return len(self._skills)

    @property
    def generated_at(self) -> str:
        return str(self._index.get("generated_at") or "")

    @property
    def load_error(self) -> str:
        return str(self._index.get("_load_error") or "")

    # -- seleksjon ------------------------------------------------------

    def _bm25(self, query_terms: Sequence[str], doc_idx: int) -> tuple[float, list[str]]:
        k1, b = 1.5, 0.75
        doc = self._docs[doc_idx]
        if not doc:
            return 0.0, []
        n = len(self._docs)
        length = len(doc)
        score = 0.0
        matched: list[str] = []
        counts: dict[str, int] = {}
        for term in doc:
            counts[term] = counts.get(term, 0) + 1
        for term in set(query_terms):
            freq = counts.get(term, 0)
            if not freq:
                continue
            matched.append(term)
            df = self._df.get(term, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * (length / self._avg_len if self._avg_len else 1.0))
            score += idf * (freq * (k1 + 1)) / denom

        # Dekningsvekt: hvor STOR ANDEL av spørringens termer traff.
        #
        # Målt 2026-08-11 uten denne: oppgaven «neo4j cypher query returns stale
        # rows after the label rename» valgte skillen `shop`, fordi den ene
        # matchen «returns» (df=1, altså maksimal IDF) kom fra en nettbutikks
        # returordning. Ren BM25 kan ikke skille «sjelden» fra «relevant» — ett
        # tilfeldig sjeldent treff slår tre topiske.
        #
        # Kvadratrot og ikke lineært: en smal, presis skill som treffer 2 av 8
        # termer skal svekkes, ikke utraderes.
        distinct = len(set(query_terms))
        if distinct:
            score *= math.sqrt(len(matched) / distinct)
        return score, sorted(matched)

    def select(self, query: str, *, limit: int = 3, min_score: float = 0.5) -> SkillSelection:
        """Velg de mest relevante skillene for en oppgave.

        `min_score` er en terskel mot støy, ikke mot fravær: at ingenting når
        over den betyr «ingen god match», ikke «finnes ikke». Skillet håndheves
        av report_missing().
        """
        terms = _tokens(query)
        if self.load_error:
            note = f"indeks kunne ikke leses: {self.load_error}"
        elif self.is_stale:
            age = self.age_seconds or 0
            note = (f"indeksen er {age / 3600:.1f} t gammel (grense {MAX_INDEX_AGE_S / 3600:.0f} t) "
                    "— dekningen er degradert til PARTIAL; bygg den på nytt med "
                    "tools/skill_catalog_index.py")
        else:
            note = ""
        if not terms:
            return SkillSelection(query, self.coverage, self.size, (), 0,
                                  self.generated_at, self._index_path,
                                  note or "spørringen hadde ingen brukbare termer")

        scored: list[ScoredSkill] = []
        for idx, skill in enumerate(self._skills):
            score, matched = self._bm25(terms, idx)
            if score < min_score:
                continue
            scored.append(
                ScoredSkill(
                    name=skill.get("name", ""),
                    score=score,
                    primary_path=skill.get("primary_path", ""),
                    primary_root=skill.get("primary_root", ""),
                    description=skill.get("description", ""),
                    matched_terms=tuple(matched),
                    name_collision=bool(skill.get("name_collision")),
                )
            )
        scored.sort(key=lambda s: (-s.score, s.name))
        return SkillSelection(
            query=query,
            coverage=self.coverage,
            considered=self.size,
            selected=tuple(scored[:limit]),
            query_terms=len(set(terms)),
            index_generated_at=self.generated_at,
            index_path=self._index_path,
            note=note,
        )


#: Svaret når dekningen ikke tillater en fravær-påstand. Bevisst en egen verdi og
#: ikke `False`/`None`: begge de to ville kollapset til «nei» i en if-test.
UNRESOLVED = "UNRESOLVED"


def report_missing(selection: SkillSelection) -> str:
    """Får vi si at det ikke finnes en skill for dette? (BL-4039)

    Returnerer:
        "MISSING"     dekningen er COMPLETE og ingenting matchet — et EKTE funn
        "PRESENT"     noe matchet
        UNRESOLVED    dekningen er PARTIAL/UNKNOWN — vi VET IKKE, og å si
                      «mangler» her ville vært et falskt funn

    Dette er invarianten i kode. Kallere som vil ha et boolsk svar må velge hva
    UNRESOLVED skal bety hos dem — og det valget blir dermed synlig i deres kode
    i stedet for å skje ved et uhell her.
    """
    if selection.selected:
        return "PRESENT"
    if not selection.coverage_complete:
        return UNRESOLVED
    if not selection.queryable:
        # Full dekning, men ingenting ble spurt om. Se SkillSelection.queryable.
        return UNRESOLVED
    return "MISSING"


def trace(selection: SkillSelection, *, stage: str, path: Path | str | None = None) -> Path | None:
    """Skriv seleksjonen til et spor, så den kan MÅLES etterpå.

    Dette er punkt 3 i oppgaven: «en seleksjon ingen kan observere er ikke
    koblet». Sporet er append-only JSONL, feiler stille (et sporingsproblem skal
    aldri felle en kode-workflow) og returnerer stien det skrev til, eller None.
    """
    p = Path(path) if path is not None else default_trace_path()
    # Sporet lagrer IKKE turteksten.
    #
    # Reviewer 2026-08-11: adapteren sender hele kodeturen inn, og `query[:400]`
    # skrev opptil 400 tegn av den — potensielt en innlimt nøkkel — til en
    # append-only fil uten retensjon. Det er samme innholdsklasse adapterens
    # egen JSON-kontrakt forbyr.
    #
    # Det som lagres i stedet er nok til å ETTERGÅ et valg uten å bevare
    # innholdet: en hash (samme tur → samme rad), lengden, og termene som
    # traff. `matched_terms` er trygge ved konstruksjon: de er snittet mellom
    # turen og katalogens ordforråd, så en hemmelighet kan ikke passere gjennom
    # dem uten å allerede stå i en SKILL.md.
    digest = hashlib.sha256(selection.query.encode("utf-8")).hexdigest()[:16]
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "query_sha256_16": digest,
        "query_chars": len(selection.query),
        **selection.to_json(),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return p
    except OSError:
        return None


def render_for_prompt(selection: SkillSelection, *, max_chars: int = 2000) -> str:
    """Gjør en seleksjon til tekst en systemprompt kan bære.

    Erstatter påstanden «Use your own faber.codex memory and skills» med de
    faktisk valgte skillene, navngitt og med sti. Under ufullstendig dekning
    SIER den det — modellen skal ikke tro at listen er uttømmende når den ikke
    er det.
    """
    if not selection.selected:
        if not selection.queryable:
            return ("No skill lookup was possible for this turn — it contained no "
                    "searchable terms. This says nothing about what the catalog holds. "
                    "Do not conclude that a relevant skill does not exist.")
        if selection.coverage_complete:
            return ("No catalog skill matched this task. The catalog was read in full "
                    f"({selection.considered} skills), so this is a measured absence.")
        return ("Skill catalog coverage is "
                f"{selection.coverage.upper()} — no skill list is available for this task. "
                "Do not conclude that a relevant skill does not exist.")

    lines = [
        f"Selected skills for this task (from {selection.considered} indexed, "
        f"catalog coverage {selection.coverage.upper()}):"
    ]
    for skill in selection.selected:
        desc = skill.description[:240]
        lines.append(f"- {skill.name} [{skill.primary_root}] — {desc}")
        lines.append(f"  path: {skill.primary_path}")
    if not selection.coverage_complete:
        lines.append("NOTE: coverage is not COMPLETE — this list may be missing relevant skills.")
    out = "\n".join(lines)
    return out[:max_chars]


def select_for_task(
    task_text: str,
    *,
    stage: str = "unspecified",
    limit: int = 3,
    index_path: Path | str | None = None,
    trace_path: Path | str | None = None,
) -> SkillSelection:
    """Én-kalls inngang for workflow-steg: last, velg, spor.

    Dette er funksjonen 13-stegs-kjeden kaller. Den feiler ikke: en manglende
    indeks gir en seleksjon med dekning UNKNOWN, og UNKNOWN forplanter seg til
    report_missing() — som da nekter å påstå fravær.
    """
    catalog = SkillCatalog.load(index_path)
    selection = catalog.select(task_text, limit=limit)
    trace(selection, stage=stage, path=trace_path)
    return selection


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: gjør katalogen konsulterbar UTENFOR prosessen.

    Et steg i kjeden som ikke kan importere denne modulen — feil repo, feil
    dependency-retning, eller en fil som holdes av en annen sesjons lease — kan
    fortsatt spørre katalogen:

        python -m agent.skill_selector --stage step3 "din oppgavetekst"

    Utskriften er JSON på stdout, med dekningen og verdiktet. Exit-koden bærer
    invarianten: 0 = skills valgt, 3 = MÅLT fravær (dekning COMPLETE, ingenting
    matchet), 4 = UNRESOLVED (dekningen tillater ikke en fravær-påstand). At
    fravær og uavklart har ULIKE koder er poenget — en kaller som behandler
    «ingen treff» og «vi vet ikke» likt, produserer falske funn.
    """
    import argparse

    ap = argparse.ArgumentParser(description="Consult the local skill catalog (BL-4057)")
    ap.add_argument("query", nargs="+", help="oppgaveteksten det skal velges skills for")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--stage", default="cli", help="hvilket steg som spør (havner i sporet)")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--no-trace", action="store_true", help="ikke skriv til sporet")
    ap.add_argument("--prompt", action="store_true",
                    help="skriv prompt-teksten i stedet for JSON")
    args = ap.parse_args(argv)

    query = " ".join(args.query)
    catalog = SkillCatalog.load(args.index)
    selection = catalog.select(query, limit=args.limit)
    if not args.no_trace:
        trace(selection, stage=args.stage)

    verdict = report_missing(selection)
    if args.prompt:
        print(render_for_prompt(selection))
    else:
        payload = selection.to_json()
        payload["verdict"] = verdict
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")

    if verdict == "PRESENT":
        return 0
    return 3 if verdict == "MISSING" else 4


if __name__ == "__main__":
    raise SystemExit(main())
