"""Observe-only tick over the governed Faber backlog.

The goal registry had no caller: goals could be promoted into it and nothing
would ever look at them, so the queue's state was only knowable by hand.  This
module closes that without granting any new authority — it reads the backlog,
measures the evidence that is actually available, runs the same
:class:`PreflightGate` and owner-gate rules the runner uses, and records the
verdict.

It deliberately cannot build, review, commit, land, or start anything.  There is
no build callback to invoke and :class:`GovernedCodeRunner` is never constructed
here.  Wiring an *executing* tick is BL-3633's own scope and needs its own gate;
this one only makes the queue observable, so a goal that is stuck is visible as
stuck instead of silently absent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.code_workflow import (
    FaberGoal,
    FaberGoalRegistry,
    PreflightGate,
    PreflightInput,
    PreflightStatus,
    owner_gate_block,
)
from agent.lease_authority import (
    check as lease_clear_via_authority,
    scope_paths as _scope_paths,
)

#: Statuses PreflightGate treats as actionable.  Mirrored here only to explain a
#: BLOCK in the readback; the gate itself remains the single decision point.
_UNKNOWN = "unknown"


@dataclass(frozen=True)
class GoalObservation:
    """What one goal's evidence actually says right now."""

    goal_id: str
    bl_ref: str
    gate: str
    state: str
    preflight: str
    stopped_by: str
    reasons: tuple[str, ...] = ()
    next_step: str = ""
    #: BL-4087 PROVENANS, IKKE GATE. `git_clean` er naa scope-relativ (se
    #: `scope_is_clean`), og da MAA det staa hvor mye skitt som faktisk finnes
    #: rundt -- ellers leses en PASS som «treet var rent», og det er en paastand
    #: ingen har maalt. -1 betyr at treet ikke lot seg lese.
    repo_dirty_files: int = -1
    #: Filene i MAALETS EGET scope som er skitne. Tom naar `git_clean` er sann.
    scope_dirty: tuple[str, ...] = ()
    #: Commiten treet sto paa da observasjonen ble gjort. MAALT, ikke oppgitt.
    git_ref: str = ""


@dataclass(frozen=True)
class ObserveResult:
    observed_at: str
    registry: str
    goals: int
    preflight_clear: int
    observations: tuple[GoalObservation, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "registry": self.registry,
            "goals": self.goals,
            # NOT "runnable": clearing preflight and the owner gate is necessary,
            # not sufficient. GovernedCodeRunner additionally requires test
            # evidence, a matching reviewer diff_id, a reviewer PASS and complete
            # prelanding DoD evidence, none of which this tick can know.
            "preflight_clear": self.preflight_clear,
            "action_taken": (
                "Read the governed backlog and evaluated preflight and the owner gate. "
                "No build, review, commit, landing, ACT, or service start was attempted — "
                "this tick has no capability to perform any of them. A goal counted in "
                "preflight_clear still has the runner's build/review/landing gates ahead of it."
            ),
            # BL-4087: hva `git_clean` NÅ betyr, sagt der resultatet leses.
            "git_clean_semantics": (
                "scope-relative: only the files each goal's own repo_scope names are "
                "required to be clean. PreflightGate's own contract says 'those leased "
                "files are clean'; measuring the whole repo contradicted it and, in a "
                "worktree shared by parallel streams, made the gate unpassable by "
                "construction (measured 2026-08-11: ~120-130 dirty files, a moving "
                "number; 7 of 7 goals blocked, "
                "uninterrupted). The surrounding dirt is not hidden — see "
                "repo_dirty_files and scope_dirty per goal."
            ),
            # Observatoeren TAR ingen lease. At maal staar igjen med kun
            # lease-grunner er derfor forventet og er selve overleveringen til
            # steg 6 -- ikke en feil, og ikke noe aa «fikse» her.
            "lease_note": (
                "This tick never claims. A goal whose only remaining reasons are "
                "lease-related has cleared everything step 4 can answer without acting; "
                "the claim itself is step 6 (agent.faber_runtime.lease_take)."
            ),
            "observations": [
                {
                    "goal_id": o.goal_id,
                    "bl_ref": o.bl_ref,
                    "gate": o.gate,
                    "state": o.state,
                    "preflight": o.preflight,
                    "stopped_by": o.stopped_by,
                    "reasons": list(o.reasons),
                    "next_step": o.next_step,
                    # BL-4087 PROVENANS. Uten disse tre er en scope-relativ
                    # `git_clean` en usagt smalning: leseren ville sett PASS og
                    # antatt et rent tre. Nå står det hvor mye skitt som faktisk
                    # er der, hvilke av MÅLETS EGNE filer som er skitne, og
                    # hvilken commit renheten ble målt mot.
                    "repo_dirty_files": o.repo_dirty_files,
                    "scope_dirty": list(o.scope_dirty),
                    "git_ref": o.git_ref,
                }
                for o in self.observations
            ],
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _porcelain(repo: str | os.PathLike[str] | None) -> "tuple[bool, frozenset[str]]":
    """``(lesbart, skitne stier)``. Uleselig tre gir ``(False, frozenset())``.

    Uleselig er IKKE rent. Kallerne skiller derfor paa flagget, ikke paa om
    mengden er tom -- en tom mengde fra et uleselig tre ville lest som «alt er
    rent», som er den samme fravaer-som-funn-feilen resten av kjeden er bygget
    for aa hindre.
    """
    if not repo:
        return False, frozenset()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, frozenset()
    if proc.returncode != 0:
        return False, frozenset()
    paths: set[str] = set()
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            entry = line[3:].strip()
            # rename-form: "gammel -> ny"; begge sider er beroert
            if " -> " in entry:
                a, b = entry.split(" -> ", 1)
                paths.add(a.strip().strip('"'))
                paths.add(b.strip().strip('"'))
            else:
                paths.add(entry.strip('"'))
    return True, frozenset(paths)


def git_head(repo: str | os.PathLike[str] | None) -> str:
    """Commiten treet staar paa. MAALT -- ikke oppgitt av et maal.

    BL-4087. `PreflightGate.REQUIRED_REFS` krever `git`, og `evidence_for` leste
    den fra `goal.evidence["git_ref"]` -- et felt INGEN produsent skriver. Alle
    sju maalene BLOKKERTE derfor paa «missing authoritative source refs: git»,
    i HVER pakke sporet holder: 495 av 495, maalt 2026-08-11.

    Det arvede BL-4029-tallet er «340 ... samples», og det staar i FEM filer --
    `task_classifier.py`, `faber_fitness.py`, `code_workflow.py`,
    `tests/test_faber_fitness.py`, `tests/test_task_classifier.py`. Ikke fire, og
    INGEN av dem sier «observations»: den ordlyden fant denne endringen paa og
    tilskrev deretter eldre kode. Tallet er dessuten 155 for lavt mot maalingen
    over. Sporet roterer ved TRAIL_LIMIT=500, saa 495 er et GULV, ikke en start.

    Det er BL-4029 L4s sirkularitet i sin minste form, ett lag lenger ut: gaten
    ble rettet, produsenten ikke. Og «autoritativ» betyr her nettopp at den ikke
    skal komme fra maalet -- en sha maalet oppgir om seg selv er et sitat.
    """
    if not repo:
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_is_clean(repo: str | os.PathLike[str] | None) -> bool:
    """Er HELE treet rent? Beholdt uendret for kallere som spoer om det.

    Merk at dette IKKE lenger er det steg 4 spoer om -- se
    :func:`scope_is_clean`.
    """
    ok, paths = _porcelain(repo)
    return ok and not paths


def scope_is_clean(repo: str | os.PathLike[str] | None, scope: str,
                   ) -> "tuple[bool, tuple[str, ...], int]":
    """Er FILENE DETTE MAALET SKAL ROERE rene? Returnerer ``(rent, skitne-i-scope, repo-skitne)``.

    BL-4087, OG DETTE ER IKKE EN LOESNING JEG FANT PAA. `PreflightGate`s egen
    docstring lister kontrakten sin i tre punkter, og punkt 2 lyder ordrett:

        2. those leased files are clean

    Implementasjonen maalte likevel `git status --porcelain` over HELE repoet.
    I et delt arbeidstre med aatte parallelle stroemmer er repo-vid renhet
    uoppnaaelig ved konstruksjon -- maalt 2026-08-11: rundt 120-130 skitne
    filer (129 ved siste lesning; tallet BEVEGER SEG, og det er poenget), og alle
    sju maal BLOKKERTE paa nettopp den grunnen, uavbrutt. Da er gaten ikke en
    gate, den er en VEGG. Samme funn som BL-4055s andre-mening, og samme
    falsifikator som BL-4029 L4 brukte: *finnes det en sekvens av legitime
    handlinger som aapner den?* Repo-vidt: nei. Scope-relativt: ja.

    ET SCOPE UTEN FILER ER IKKE RENT. Det er UKJENT, og en ukjent mengde kan
    ikke vaere disjunkt fra noe -- samme regel som `LandingScopeGate` paa steg 11.

    OG DEN VIDERE SKITTEN FORSVINNER IKKE, DEN BLIR REGISTRERT. Tredje
    returverdi er antallet skitne filer i repoet, som kalleren skriver inn i
    observasjonen. Ellers ville en PASS lest som «treet var rent», og det er en
    paastand ingen har maalt. En maalings-mangel degraderer dekningen; en
    POLICY-avgrensning registreres -- og dette er det siste.
    """
    ok, dirty = _porcelain(repo)
    if not ok:
        return False, (), -1
    paths = _scope_paths(scope)
    if not paths:
        return False, (), len(dirty)
    inside = tuple(sorted(p for p in paths if p in dirty))
    return (not inside), inside, len(dirty)


#: BL-4029 L3 -- scope tokens mapped to a CONTENT marker, never a directory or
#: remote name.  Measured 2026-08-10: four trees on .15 carry the remote
#: ``supertedai/AGI.git`` -- including ``hermes-agent`` itself -- because that
#: remote hosts disjoint lineages.  A check on name or remote answers the wrong
#: question; only content says whether the codebase is here.
SCOPE_MARKERS: dict[str, tuple[str, ...]] = {
    "agi": ("tools/self_state_aggregator.py", "apis"),
    "hermes-agent": ("agent/code_workflow.py",),
}

#: Where each scope would live on this host, if it lives here at all.
SCOPE_ROOTS: dict[str, str] = {
    "hermes-agent": "/home/agent/agent-layer/hermes-agent",
    "agi": "/home/agent/AGI",
}


def scope_is_executable_here(repo_scope: str) -> tuple[bool, str]:
    """Is the goal's target codebase present on THIS host?

    Returns ``(executable, note)``.  A scope this resolver does not recognise
    returns ``True`` with a note: an unknown scope must not be silently
    rejected -- that would turn a gap in this table into a verdict about the
    world, which is the failure class BL-4003 spent eight instances on.
    """
    text = (repo_scope or "").lower()
    named = [tok for tok in SCOPE_MARKERS if tok in text]
    if not named:
        return True, "scope not recognised by this resolver — not judged"

    missing = []
    for tok in named:
        root = Path(SCOPE_ROOTS.get(tok, ""))
        markers = SCOPE_MARKERS[tok]
        if not root or not all((root / m).exists() for m in markers):
            missing.append(tok)
    if not missing:
        return True, ""
    # A goal whose scope spans several codebases is executable here only if the
    # part that lives here is the whole of it.
    return False, (
        f"codebase absent on this host: {', '.join(missing)} "
        f"(content markers not found)"
    )


#: BL-4029 / ADR-062 krav (b) — UAVHENGIG OPPSLAG.
#:
#: `evidence["lease"]` er noe PRODUSENTEN skrev. Gaten som leser den, leser en
#: paastand — og en paastand er noeyaktig det reviewer BLOKKERTE i BL-3673
#: (`cab10c5f9`: "jeg skrev en post for aa faa en gate til aa slippe meg gjennom").
#:
#: Autoritetsruten `/surface/lease/check` paa `.12` svarer paa noe ANNET: om det
#: FINNES en lease, og hvem som eier den. Produsenten kan ikke endre det svaret uten
#: aa faktisk ta en lease -- altsaa uten at noe i verden endrer seg.
#:
#: BL-4059: `lease_clear_via_authority`, `_scope_paths`, token-lesingen og
#: HTTP-laget BODDE her. De er flyttet til `agent.lease_authority` og importeres
#: tilbake oeverst -- med vilje, ikke av ryddetrang. Da steg 6 fikk lov til aa TA
#: leasen, fikk `check` og `claim` samme krav: SAMME token, SAMME vert, SAMME
#: sti-sett. To kopier ville kunne divergere paa noeyaktig det som var hullet under
#: -- en token-fil produsenten selv kan slaa av -- og da ville vi verifisert én
#: mengde og leaset en annen.


def _resolve_lease_clear(ev: Mapping[str, Any]) -> tuple[bool, str]:
    """Autoriteten avgjoer. UVERIFISERT er IKKE "clear".

    FOERSTE VERSJON FALT TILBAKE PAA `evidence["lease"]` NAAR AUTORITETEN IKKE
    SVARTE, og det var et hull produsenten selv kunne aapne:

        `_surface_token()` leser SURFACE_RECEIPT_TOKEN eller token-fila -- BEGGE
        paa `.15`, BEGGE eid av `agent`, som ER produsentens identitet. Produsenten
        kunne `rm` fila, eller `chmod 0644` den, og faa tom token -> `None` ->
        fallback -> sin egen paastand aeret.

    Ironien er skarp: modus-sjekken er en HERDINGSKONTROLL, og den var den billigste
    bryteren for aa skru verifiseringen AV. **En kontroll som feiler inn i aa stole
    paa den begrensede parten, er en kontroll den parten kan slaa av.**

    Det er ADR-062s terminus omskrevet: en tillitsgrense kan ikke uttrykkes i en fil
    den utrygge parten kan skrive -- og her: **en verifisering kan ikke avhenge av et
    kreditiv den verifiserte parten kontrollerer, og maa aldri feile aapent til dens
    paastand.**

    Naa: kan vi ikke verifisere, er svaret FALSE med en egen begrunnelse. Aa blokkere
    naar autoriteten er nede er riktig for en gate som skal hindre uautorisert
    landing -- og det gjoer et autoritets-utfall SYNLIG i stedet for at systemet
    stille faller tilbake til posturen fra foer ruten fantes.
    """
    paths = _scope_paths(str(ev.get("repo_scope", "")))
    if not paths:
        # Et maal uten filer i scope kan ikke ha en verifiserbar lease. Foer var
        # dette samme hull via en stillere vei: tom liste -> None -> produsentens
        # paastand.
        return False, "scope lister ingen filer — lease kan ikke verifiseres"

    verified, note = lease_clear_via_authority(paths)
    if verified is not None:
        return verified, note
    return False, (f"lease UVERIFISERT ({note}) — evidensen er produsentens egen "
                   f"paastand og aeres ikke")



#: Registeret kontrakt-referanser SLAAS OPP I. Sti, ikke pakke -- MWP-registeret
#: er dokumenter paa disk, ikke en modul.
MWP_DOCS = os.environ.get(
    "MWP_DOCS", "/home/agent/agent-layer/mwp-uosh-automation-01/docs")

#: Statusordene et dokument kan BAERE som betyr «akseptert». Maalt mot registeret
#: 2026-08-11: `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`,
#: `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED / LIVE_WRITER_CANARY`,
#: `OPEN`, `PROPOSED / OWNER-REVIEW / RUNTIME-GATED`.
#:
#: MERK at «akseptert arkitektur» IKKE er «implementert». Gaten paa steg 7 spoer
#: om en DESIGNBESLUTNING finnes og er tatt -- ikke om den er bygget. Det er to
#: spoersmaal, og aa slaa dem sammen ville gjort steg 7 til en umulig gate igjen
#: (BL-4029 L4).
#: HELE FOERSTE SEGMENT maa vaere ett av disse. IKKE substring.
#:
#: Reviewer maalte tre LEVENDE dokumenter der substring-matching snudde
#: polariteten -- og det foerste er en CAD, altsaa paa den gatede stien:
#:
#:   CAD-EFC-REPO-001              "Audit complete; open lanes recorded"  -> accepted
#:   BL-HERMES-INGEST-001          "PARTIAL / CANARY_COMPLETE_..."        -> accepted
#:   BL-HERMES-MEMORY-FABRIC-001   "PARTIAL / CANARY_COMPLETE_..."        -> accepted
#:
#: Og syntetisk: `INCOMPLETE`, `NOT ACCEPTED`, `IKKE VEDTATT` -- alle accepted.
#: Aa sjekke `_REJECTED_MARKERS` foerst hjelper ikke: negasjonen bor som PREFIKS
#: eller kvalifikator (`IN-`, `NOT `, `IKKE `, `PARTIAL /`), ikke som eget ord.
#: `_COMPLETE_` inne i et sammensatt token er husstil i nettopp dette registeret.
#: UTLEDET fra registeret, ikke listet. Maalt 2026-08-11 over 91 dokumenter:
#: hodene som betyr akseptert er `ACCEPTED_ARCHITECTURE` (20), `ACCEPTED_SCHEMA`
#: (1) og `ACCEPTED` (1). Foerste utkast listet to av dem og felte derfor
#: `ADR-H10-SEMANTIC-BOUNDARY-001` -- en ekte akseptert ADR -- fordi
#: `ACCEPTED_SCHEMA` ikke sto der. En liste over former er alltid ett dokument
#: bak registeret; en REGEL er det ikke.
_ACCEPTED_OTHER = frozenset({"VEDTATT", "UTFOERT", "UTFØRT", "VERIFIED", "FRESH"})


def _is_accepted_head(head: str) -> bool:
    return (head == "ACCEPTED" or head.startswith("ACCEPTED_")
            or head in _ACCEPTED_OTHER)
_REJECTED_HEADS = frozenset({
    "SUPERSEDED", "WITHDRAWN", "REJECTED", "OBSOLETE", "DEPRECATED",
})
#: Ord som NEKTER -- som HELE TOKEN, aldri som substring.
#:
#: Foerste utkast matchet med `in`, og da flyttet BLOCK 2s defekt seg hit i
#: stedet for aa forsvinne. Maalt paa to LEVENDE aksepterte ADR-er:
#:
#:   ACCEPTED / IMPLEMENTED_NOT_LOADED / RESTART_GATE   `NOT` inni et token
#:   ACCEPTED_ARCHITECTURE / UNBLOCKED                  `BLOCKED` inni `UNBLOCKED`
#:
#: Begge ble falskt BLOKKERT. Min egen test stavet markoeren `"NOT "` med
#: mellomrom mens implementasjonen stavet den `"NOT"` -- testens vokabular var
#: mer forsiktig enn kodens.
#:
#: Tokeniseringen splitter IKKE paa `_`: `IMPLEMENTED_NOT_LOADED` er ETT ord i
#: dette registerets husstil, og det er nettopp derfor substring var galt.
_NEGATIONS = frozenset({"IKKE", "NOT", "NO", "PARTIAL", "PENDING", "INCOMPLETE",
                        "BLOCKED", "UNVERIFIED"})


def _status_tokens(line: str) -> "frozenset[str]":
    """Statuslinja som HELE ord. Splitter paa mellomrom og skilletegn, ikke `_`."""
    out, word = [], []
    for ch in line.upper():
        if ch.isalnum() or ch == "_":
            word.append(ch)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return frozenset(out)


def _status_word(line: str) -> str:
    """Statusens FOERSTE segment, som ett ord. `A / B / C` -> `A`.

    Registeret skriver `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`: hodet baerer
    beslutningen, halen baerer forbeholdene. Vi doemmer paa hodet, og vetoer paa
    negasjon hvor som helst i linja.
    """
    head = line.split("/")[0].split(";")[0].split(",")[0].strip(" *:`")
    return head.split()[0].upper() if head.split() else ""

#: `F5`, `F12`: fase-halen ADR-064 definerer.
_PHASE_SHAPED = re.compile(r"^F\d+$", re.IGNORECASE)
#: En ekte registerreferanse ENDER i en identifikator: `-001`, `-062`, `-F5`.
#: Uten det kravet holdt `ADR-HERMES-CHAIN` -- som navngir INTET dokument --
#: til aa slaa opp `ADR-HERMES-CHAIN-DRIVE-001.md` og faa `accepted`. En
#: avkortet prefiks-streng klarerte altsaa steg 7. Samme hull som
#: `ADR-DOES-NOT-EXIST-999`, gjennom en tredje doer -- og de to foerste ble
#: lukket i hver sin runde uten at noen spurte om det fantes flere doerer.
_REGISTER_REF = re.compile(
    r"^(ADR|CAD|BL)-(?:[A-Z0-9][A-Z0-9.-]*-)?(?:\d+|F\d+)$", re.IGNORECASE)



def _choose_document(hits: "list", ref: str):
    """Hvilken fil EIER statusen for dette nummeret? (BL-4095, reviewer BLOCK 3)

    Foerste utkast tok `hits[0]`. Maalt: med `ADR-047.md` (PROPOSED) og
    `ADR-047-F5.md` (ACCEPTED) i samme katalog sorterer `-` (0x2D) foer `.`
    (0x2E), saa FASE-fila vant deterministisk -- og en fases aksept ble kreditert
    hele beslutningen. Motsatt polaritet ogsaa maalt: base ACCEPTED + fase
    SUPERSEDED ga falsk BLOCK.

    ADR-064/BL-4053: flere filer per nummer er LOVLIG, og nøyaktig én erklaerer
    `adr_role: base` og eier statusen. Rekkefoelgen her foelger den regelen:

      1. eksakt `{ref}.md`
      2. den ene som erklaerer `adr_role: base`
      3. ellers: INGEN -- kalleren melder `unverifiable`, aldri et sorteringsvalg
    """
    if not hits:
        return None
    low = ref.lower()
    # D2: prefikset maa slutte paa en GRENSE. Uten det slo `ADR-J` opp
    # `ADR-JS-WM-001.md` og fikk `accepted` -- en to-tegns streng som klarerte
    # steg 7. Samme hull som `ADR-DOES-NOT-EXIST-999`, gjennom en annen doer.
    # Og `ADR-047` traff `ADR-0470.md`, et ANNET nummers dokument.
    hits = [p for p in hits
            if p.stem.lower() == low or p.stem.lower().startswith(low + "-")]
    if not hits:
        return None
    exact = [p for p in hits if p.stem.lower() == low]
    if exact:
        return exact[0]
    if len(hits) == 1:
        # Slug-formen er lovlig og i bruk: `ADR-TRUTH-001` ->
        # `ADR-TRUTH-001-cross-surface-canonical-truth.md`. Men en FASE er det
        # ikke: `ADR-047` med bare `ADR-047-F5.md` skal ikke faa fasens aksept
        # kreditert beslutningen (ADR-064/BL-4053). Snarveien var utestet, og
        # den gjenaapnet BLOCK 3 i ett-treffs-tilfellet.
        rest = hits[0].stem[len(ref):].lstrip("-")
        if _PHASE_SHAPED.match(rest):
            return None
        return hits[0]
    based = [p for p in hits
             if "adr_role: base" in p.read_text(encoding="utf-8", errors="replace")[:1200].lower()]
    return based[0] if len(based) == 1 else None

def resolve_contract_ref(ref: str, *, docs: str | None = None) -> "tuple[str, str]":
    """SLAA OPP en kontrakt-referanse i registeret. Returnerer ``(status, note)``.

    BL-4095, G6 -- OG DETTE ER HULLET ALT ANNET HANG PAA. Ingen gate i kjeden
    verifiserte en kontrakt-referanse mot NOE register. `DesignGate` sjekket at
    ``source_refs["cad"]`` og ``["adr"]`` var IKKE-TOMME STRENGER, pluss en
    ``cad_status``/``adr_status`` PRODUSENTEN selv paastod. `BlGate` det samme
    for ``bl``. `parse_contract_ref` i klassifisereren sjekker FORM, og sier det
    selv.

    Konsekvensen, maalt: `ADR-DOES-NOT-EXIST-999` klarerte steg 7 NOEYAKTIG som
    en ekte referanse, saa lenge noen hadde skrevet `accepted` i statusfeltet.
    Det er kontrollen-som-ikke-kan-feile, plassert i den gaten som avgjoer om
    designgjennomgang har skjedd.

    FIRE UTFALL, med vilje ikke to:

    ``accepted``       dokumentet FINNES og baerer et akseptert-ord
    ``proposed``       dokumentet finnes, men er ikke akseptert enda
    ``missing``        referansen har registerform, men INGEN fil svarer til den
    ``unverifiable``   referansen peker utenfor registeret vi kan lese herfra

    Den siste er den viktige. `ADR-062` er et SYMBIOSE-nummer, og Symbioses
    ADR-er bor i `planning/` og vaulten paa `.13` -- ikke naabart herfra. Aa
    melde det som `accepted` ville vaert aa paastaa en verifisering vi ikke
    gjorde; aa melde det som `missing` ville vaert aa anklage et dokument som
    trolig finnes. UVERIFISERBAR er det sanne svaret, og den passerer ikke
    `DesignGate.ADR_OK` -- fail-closed uten aa lyve om aarsaken.
    """
    text = (ref or "").strip()
    if not text:
        return "unknown", "ingen referanse oppgitt"
    if not _REGISTER_REF.match(text):
        # En filsti eller modulreferanse er en gyldig kontraktFORM (se
        # `task_classifier.parse_contract_ref`), men den bor ikke i dette
        # registeret. Vi paastaar ingenting om den.
        return "unverifiable", f"{text}: ikke en registerreferanse — ingen oppslag gjort"

    root = Path(docs or MWP_DOCS)
    if not root.is_dir():
        # Uleselig register er IKKE et tomt register. Samme regel som
        # `_porcelain`: fravaer av svar er ikke et svar.
        return "unverifiable", f"registeret {root} er ikke lesbart herfra"

    # Case-insensitiv: `_REGISTER_REF` er IGNORECASE, saa globben maa vaere det
    # ogsaa. Ellers gir `adr-hermes-ingest-001` "missing" for et dokument som
    # FINNES -- altsaa en anklage mot et ekte dokument, som er nettopp det
    # `unverifiable` finnes for aa unngaa.
    low = text.lower()
    hits = sorted(p for p in root.glob("*.md") if p.name.lower().startswith(low))
    if not hits:
        upper = text.upper()
        if upper.split("-")[0] in {"ADR", "BL"} and upper.split("-")[-1].isdigit()                 and len(upper.split("-")) == 2:
            # ADR-062 / BL-4087: Symbioses egne numre. De bor paa `.13`.
            return "unverifiable", (
                f"{text}: Symbiose-nummer — registeret bor i planning/ og vaulten "
                f"paa .13, ikke naabart fra denne verten")
        return "missing", f"{text}: ingen fil i {root} svarer til referansen"

    chosen = _choose_document(hits, text)
    if chosen is None:
        # Reviewer: meldingen brukte det YTRE `hits` og fortalte derfor
        # `ADR-H10-SEMANTIC-BOUNDARY-0` at den hadde et tvetydig-base-problem,
        # naar den egentlig var en AVKORTING. En gate som forklarer seg selv
        # feil er klassen denne BL-en har jaktet paa hele veien.
        low_ = text.lower()
        on_boundary = [p for p in hits
                       if p.stem.lower() == low_ or p.stem.lower().startswith(low_ + "-")]
        if not on_boundary:
            return "missing", (
                f"{text}: ingen fil svarer paa referansen — naermeste treff er en "
                f"annen identifikator ({', '.join(p.stem for p in hits[:2])})")
        return "unverifiable", (
            f"{text}: {len(on_boundary)} filer svarer til nummeret og ingen erklaerer "
            f"`adr_role: base` — hvilken som eier statusen er uavklart "
            f"(ADR-064/BL-4053)")
    doc = chosen.read_text(encoding="utf-8", errors="replace")
    line = ""
    for raw in doc.splitlines()[:12]:
        if raw.strip().lower().startswith("**status:**"):
            line = raw.split("**", 2)[-1].strip(" *:`")
            break
    if not line:
        # D3: var `hits[0]`, altsaa en ANNEN fil enn den som ble lest.
        return "proposed", f"{chosen.name}: fant dokumentet, men ingen Status-linje"
    head = _status_word(line)
    if head in _REJECTED_HEADS:
        return "rejected", f"{chosen.name}: {line}"
    if _status_tokens(line) & _NEGATIONS:
        # Negasjon vetoer, uansett hvor den staar. `PARTIAL / CANARY_COMPLETE_X`
        # er ikke akseptert bare fordi halen inneholder et positivt ord.
        return "proposed", f"{chosen.name}: {line}"
    if _is_accepted_head(head):
        return "accepted", f"{chosen.name}: {line}"
    return "proposed", f"{chosen.name}: {line}"

def evidence_for(goal: FaberGoal, *, git_clean: bool, git_ref: str = "") -> PreflightInput:
    """Build the goal's preflight input from what it actually recorded.

    Nothing is upgraded on the way in: a status the goal never established stays
    unknown, so the gate blocks for a reason that names the missing evidence.
    """
    ev = goal.evidence
    # PreflightGate requires an authoritative reference per source.  They are
    # read only from fields a governance step actually recorded -- a goal that
    # never established one is missing it, and the gate names it in the BLOCK.
    refs = {}
    for name, value in (
        # BL-4087: `git` MAALES (se `git_head`) og faller tilbake paa maalets eget
        # felt bare hvis maalingen ikke lot seg gjoere. Rekkefoelgen er poenget:
        # den autoritative kilden foerst, maalets selvrapport som nodloesning.
        ("git", git_ref or ev.get("git_ref", "")),
        ("lease", ev.get("lease_ref", "")),
        ("cad", goal.cad_ref),
        ("adr", goal.adr_ref),
        ("bl", goal.bl_ref),
        ("obsidian", ev.get("obsidian_ref", "")),
    ):
        if str(value).strip():
            refs[name] = str(value)
    return PreflightInput(
        git_clean=git_clean,
        # ADR-062 (b): AUTORITETEN avgjoer. Uverifisert er ikke "clear" -- se
        # _resolve_lease_clear for hvorfor fallback til evidensen var et hull
        # produsenten selv kunne aapne.
        lease_clear=_resolve_lease_clear(ev)[0],
        # BL-4095 G6: statusen SLAAS OPP i registeret, den tas ikke fra maalet.
        # Samme regel som `git_head`: maalets selvrapport er noedloesning, ikke
        # foersteprioritet. Uten dette kunne `ADR-DOES-NOT-EXIST-999` klarere
        # steg 7 like godt som en ekte referanse.
        cad_status=resolve_contract_ref(goal.cad_ref)[0]
        if goal.cad_ref else str(ev.get("cad_status", _UNKNOWN)),
        adr_status=resolve_contract_ref(goal.adr_ref)[0]
        if goal.adr_ref else str(ev.get("adr_status", _UNKNOWN)),
        bl_status=str(ev.get("bl_status", _UNKNOWN)),
        obsidian_status=str(ev.get("obsidian_status", _UNKNOWN)),
        source_refs=refs,
        **dict(zip(("scope_executable", "scope_note"),
                   scope_is_executable_here(str(ev.get("repo_scope", ""))))),
    )


def observe_goal(goal: FaberGoal, *, git_clean: bool, gate: PreflightGate,
                 git_ref: str = "") -> GoalObservation:
    """Evaluate one goal without touching it."""
    result = gate.evaluate(evidence_for(goal, git_clean=git_clean, git_ref=git_ref))
    # The runner's own predicate, imported rather than restated: a copy here
    # would silently diverge the moment the runner grows a condition.
    held_by = owner_gate_block(goal)
    if result.status is not PreflightStatus.PASS:
        stopped_by = "preflight"
    elif held_by:
        stopped_by = "owner_gate"
    else:
        stopped_by = "none"
    return GoalObservation(
        goal_id=goal.goal_id,
        bl_ref=goal.bl_ref,
        gate=str(goal.evidence.get("gate", "")).strip().lower() or "(unset)",
        state=goal.state.value,
        preflight=result.status.value,
        stopped_by=stopped_by,
        reasons=result.reasons,
        next_step=goal.next_step,
    )


def observe(
    registry: FaberGoalRegistry,
    *,
    repo_paths: Mapping[str, str] | None = None,
) -> ObserveResult:
    """Read the whole backlog and report what each goal is waiting for."""
    gate = PreflightGate()
    head_cache: dict[str, str] = {}
    observations = []
    for goal in sorted(registry.all(), key=lambda g: (g.bl_ref, g.goal_id)):
        repo = (repo_paths or {}).get(goal.goal_id, "")
        if repo not in head_cache:
            head_cache[repo] = git_head(repo)
        # BL-4087: SCOPE-relativ renhet, per maal -- ikke repo-vid, én gang for
        # alle. Cachen laa paa `repo` og var derfor blind for at ulike maal
        # eier ulike filer i det SAMME treet. Det var ikke en optimalisering
        # som ble feil; det var svaret paa feil spoersmaal, mellomlagret.
        clean, scope_dirty, repo_dirty = scope_is_clean(
            repo, str(goal.evidence.get("repo_scope", "")))
        obs = observe_goal(goal, git_clean=clean, gate=gate, git_ref=head_cache[repo])
        observations.append(replace(
            obs, repo_dirty_files=repo_dirty, scope_dirty=scope_dirty,
            git_ref=head_cache[repo]))
    return ObserveResult(
        observed_at=_now(),
        registry=str(registry.path) if registry.path else "(memory)",
        goals=len(observations),
        preflight_clear=sum(1 for o in observations if o.stopped_by == "none"),
        observations=tuple(observations),
    )


#: Ticks kept in the trail.  Bounded before anything schedules this, per BL-813:
#: an append-only file a timer writes to is unbounded by construction.
TRAIL_LIMIT = 500


def record(result: ObserveResult, path: str | os.PathLike[str]) -> Path:
    """Append the tick to a bounded trail and refresh the latest readback."""
    target = Path(path).expanduser()
    # A ".jsonl" target would make with_suffix() return the same path, so the
    # readback write would truncate the trail it had just appended to.
    trail = target.with_name(target.stem + ".trail.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(trail, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.to_json(), ensure_ascii=False) + "\n")
    try:
        lines = trail.read_text(encoding="utf-8").splitlines()
        if len(lines) > TRAIL_LIMIT:
            trail.write_text("\n".join(lines[-TRAIL_LIMIT:]) + "\n", encoding="utf-8")
    except OSError:
        pass
    target.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one observe-only tick over the governed Faber backlog. Never builds or lands."
    )
    parser.add_argument(
        "--registry",
        help="Faber goal registry (default: $HERMES_HOME/faber/goals.json)",
    )
    parser.add_argument("--record", help="Write the readback here (a .jsonl trail is kept alongside)")
    parser.add_argument("--repo", action="append", default=[], metavar="GOAL_ID=PATH",
                        help="Measure git cleanliness for a goal's target tree (repeatable)")
    def block(*reasons: str) -> int:
        # stderr, not stdout: a scheduled caller sends stdout to /dev/null because
        # --record already persists the readback, so a BLOCK printed to stdout is a
        # silent failure -- exactly the absence this module exists to remove.
        print(json.dumps({"status": "BLOCK", "reasons": list(reasons)}, ensure_ascii=False), file=sys.stderr)
        return 2

    args = parser.parse_args(argv)
    home = os.environ.get("HERMES_HOME", "").strip()
    registry_path = args.registry or (os.path.join(home, "faber", "goals.json") if home else "")
    if not registry_path:
        return block("no registry: pass --registry, or set HERMES_HOME (several Hermes profiles exist)")
    registry_path = os.path.expanduser(registry_path)
    # Reporting "0 goals" for a path that is not there is the silent absence this
    # module exists to remove, so a missing registry is a BLOCK, not an empty run.
    if not os.path.exists(registry_path):
        return block(f"registry does not exist: {registry_path}")
    repo_paths = {}
    for item in args.repo:
        goal_id, _, path = item.partition("=")
        if not goal_id or not path:
            return block(f"--repo expects GOAL_ID=PATH, got {item!r}")
        repo_paths[goal_id] = path
    result = observe(FaberGoalRegistry(registry_path), repo_paths=repo_paths)
    if args.record:
        record(result, args.record)
    print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
