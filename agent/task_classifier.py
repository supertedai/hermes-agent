# BL-4056 — steg 3 (`ranking_planning_architecture`): HVA SLAGS oppgave er dette?
"""Klassifiser en oppgave som BL (arbeidsenhet) eller ADR (arkitekturvedtak).

DEFEKTEN
--------
Kjeden har ``BlGate`` (steg 5) og ``DesignGate`` (steg 7), men ingenting spør
FØRST hva slags oppgave den har fått. Alt behandles som en kodeendring med et
BL-nummer. En forespørsel som egentlig flytter en grense — autonomi, tillit,
dataflyt, hvem som eier hva — går rett i bygging, og vedtaket blir aldri
skrevet ned. Det er ikke at gaten sier feil; det er at spørsmålet ikke stilles.

``ADR-062 V5`` er presedensen og står i klartekst i
``faber_control_bridge.run_all``: *«Aa gi denne stien landingsevne er en
autonomi-grense-endring (ADR-062 V5) og hard-limit #3 — Mortens beslutning.»*
Den setningen er hardkodet fordi et menneske skrev den. Ingenting i kjeden
kunne ha utledet den.

SKJEVHETEN, SAGT HØYT
---------------------
En klassifiserer feiler ikke tilfeldig. Den feiler ALLTID mot den lette
klassen, fordi BL er billigere for den som klassifiserer: ett nummer, ingen
designrunde, ingen uavhengig vurderer. Det er nøyaktig slik en autonomi-grense
flyttes uten at noen vedtok den.

Derfor er modulen bygget rundt én strukturell påstand:

    **Ingen signal kan argumentere FOR den billige klassen.**

Se :class:`Disposition`. Den har tre verdier — ``ADR``, ``DOUBT``,
``DESIGN_REVIEW`` — og ingen ``BL``. Et signal kan bare flytte oppgaven
OPPOVER i kostnad. ``BL`` nås ikke ved at noe taler for den; den nås ved at
ingenting taler mot den OG at proposeren har lagt fram positiv evidens for at
endringen er reversibel og bor inne i en eksisterende kontrakt.

Tvil er en egen klasse, ikke en avrunding. :data:`TaskClass.DOUBT` eskalerer.
Den gjetter ikke BL fordi BL er billigere.

DEN ANDRE SKJEVHETEN: Å ERKLÆRE SEG FRI
----------------------------------------
Og den fyrer BEGGE veier. Et ærlig *ja* — ``declared_trust_boundary_change=True``
— er i seg selv et ADR-signal. Første utkast håndterte bare ``False`` og
``None``, og reviewer målte følgen: et ærlig ja ga null treff og dermed BL,
mens det å la feltet stå ubesvart ga DOUBT. **Å svare sant var billigere enn å
la være å svare.** Det er den samme skjevheten som modulen er bygget mot, snudd
inn i selve erklæringsmekanismen.

Signalene kommer fra to kilder, og de er ikke likeverdige:

======================  =====================================================
``source="declared"``   proposeren skrev det (``declared_trust_boundary_change``)
``source="text"``       forespørselens egen ordlyd (tittel + beskrivelse)
``source="measured"``   filstier og diff — det som faktisk endres
======================  =====================================================

Når en erklæring sier *nei* og teksten sier *ja*, er det IKKE uavgjort som
løses til fordel for erklæringen. **Du kan ikke erklære deg vekk fra et ord du
selv skrev.** Erklæringen er det den som vil bygge, skriver om seg selv;
teksten er det den som ba om arbeidet, skrev. Den som blir overprøvd er
proposeren.

Mekanismen som håndhever det er enkel og verdt å si presist, fordi det er lett
å tro at det er :data:`Signal.TEXT_STRUCTURE_DISAGREEMENT` som gjør jobben:
**det er det ikke.** Det som håndhever regelen er at leksikalske treff bærer
``Disposition.ADR`` og at ingen erklæring kan trekke fra. Uenighetstreffet er
per konstruksjon redundant — det finnes bare når et ADR-treff allerede finnes.
Det beholdes fordi *nektelsen* er noe en senere leser trenger å se i
journalen, ikke fordi det binder. (Reviewer fant at det var dekorativt så lenge
det bar ``DOUBT``; det bærer nå ``ADR``, som er klassen det uansett havner i,
slik at ingen kan sitere det som en kontroll det ikke er.)

Dette er samme lærdom som ``PreflightGate`` (ADR-062 V4) og BL-3673
(``cab10c5f9``, «jeg skrev en post for aa faa en gate til aa slippe meg
gjennom»): en gate som kan passeres ved å skrive en status, lærer folk å
skrive statuser.

SEKVENSEN — OG FELLEN SOM ALLEREDE ER GÅTT I ÉN GANG
-----------------------------------------------------
``PreflightGate`` sto på ``preflight_clear: 0`` av 7 over 340 samples fordi
den krevde artefakter kjeden produserer SENERE. Falsifikatoren — *finnes det
en sekvens av legitime handlinger som åpner denne?* — hadde ikke noe svar.

Den fellen gjelder her og: **blast-radius kan ikke måles på steg 3.** Diffen
finnes ikke ennå. Derfor er den valgfri her, og fravær blokkerer ikke — mens
et ANSLAG som overskrider :class:`~agent.code_workflow.ScopeBudget` utløser
designrunde. Den ekte målingen skjer på steg 8, hvor ``ScopeBudget`` allerede
kjører, og mates tilbake via :meth:`TaskClassifier.reclassify_on_measurement`.

Skrallen går én vei. :meth:`~TaskClassifier.reclassify_on_measurement` kan
stramme til, aldri løsne — en oppgave som ble ADR på steg 3 blir ikke BL på
steg 8 fordi diffen ble liten. Det er testet, ikke bare skrevet.

ADR-NUMRE HÅNDPLUKKES IKKE — OG DENNE MODULEN DELER IKKE UT NOEN
-----------------------------------------------------------------
5. august 2026 tok fem strømmer fem numre for hånd i samme time. ADR-054 og
ADR-055 fikk to vedtak hver (BL-3824). ADR-054 står permanent tomt.
``tools/allocate_adr.py`` fantes hele tiden — ingen kalte den, fordi regelen
bare navnga BL-varianten.

Klassifisereren minter derfor ingenting og VALIDERER ingen numre, og grunnen
er målt: allokatoren skriver et bart ``ADR-065`` til stdout, byte-identisk med
et håndskrevet. Et «kvittering»-felt som tar imot den strengen ville vært en
kontroll som ikke kan feile — verre enn ingen, fordi den blir sitert som en.
Det den gjør er å nekte steg 3 å produsere et nummer i det hele tatt, og peke
på allokatoren ved navn (:data:`ADR_ALLOCATOR_CMD`).

Og: **et ADR-nummer kan legitimt bæres av flere dokumenter.** ADR-042, ADR-043
og ADR-047 har to filer hver i dag (målt av ``tools/mwp_register_bridge.py``,
commit ``1a35c9d05``); ADR-047 er ÉN beslutning i fem faser og skal IKKE
renummereres. :func:`parse_adr_ref` godtar derfor både ``ADR-047`` og
siteringsformen ``ADR-047-F5``, og flerhet er aldri en kollisjon her.

HVA DENNE MODULEN IKKE HINDRER — LES DETTE FØR DU SITERER DEN
---------------------------------------------------------------
En proposer som erklærer ``False`` på alt OG skriver en beskrivelse som unngår
hvert eneste ord i :data:`TRUST_TERMS`, får BL. Det er ikke en bug som kan
lukkes her: teksten er det eneste uavhengige vitnet steg 3 har, og en tekst
kan skrives om.

Det som gjør skaden begrenset er at klassifiseringen LAGRES med evidensen sin
(:class:`Classification.hits`), slik at steg 7 og steg 10 — og et menneske
etterpå — kan se hvilke signaler som ble konsultert og hva de så. Fraværet av
et treff er et registrert faktum, ikke en stillhet.

Og et tall som IKKE skal siteres som mer enn det er. Kjørt mot de sju levende
Faber-målene 2026-08-11 gir modulen 2 ADR / 5 DOUBT / 0 BL. Begge ADR-ene
drives utelukkende av ordet ``autonom*`` i tittelen, og alle fem DOUBT-ene av
«du svarte ikke» — uten et eneste innholdssignal. Det er fordi ingen produsent
skriver grensesvarene inn i ``goals.json`` ennå (se
``faber_control_bridge.proposal_from_goal``). Splitten måler altså hvilke
felter som er utfylt, ikke noe om målene. Den er et utgangspunkt for
produsentsiden, ikke en påstand om porteføljen.

Modulen er bevisst uten sideeffekter, som resten av ``code_workflow``-rammen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping, Protocol, Sequence

from agent.code_workflow import ScopeBudget

__all__ = [
    "TaskClass",
    "Disposition",
    "Signal",
    "Reversibility",
    "SignalHit",
    "TaskProposal",
    "MeasuredScope",
    "Classification",
    "TaskClassifier",
    "DesignReviewRequest",
    "IndependentDesignReviewer",
    "UnavailableReviewer",
    "assert_independent_reviewer",
    "parse_adr_ref",
    "parse_contract_ref",
    "ADR_ALLOCATOR_CMD",
    "ADR_ALLOCATOR_HOST",
]


class TaskClass(str, Enum):
    """Hva slags oppgave dette er. Rangert etter kostnad, billigst først."""

    #: Arbeidsenhet: reversibel, innenfor en eksisterende kontrakt.
    BL = "BL"
    #: Kan ikke klassifiseres på evidensen. Eskalerer. Gjetter IKKE BL.
    DOUBT = "DOUBT"
    #: Arkitekturvedtak. Må designes og få uavhengig vurdering før bygging.
    ADR = "ADR"


#: Kostnadsrekkefølge. Brukes av skrallen i
#: :meth:`TaskClassifier.reclassify_on_measurement` — indeksen kan øke, aldri synke.
_CLASS_ORDER: tuple[TaskClass, ...] = (TaskClass.BL, TaskClass.DOUBT, TaskClass.ADR)


class Disposition(str, Enum):
    """Hva ETT signal kan gjøre med klassifiseringen.

    Legg merke til hva som IKKE står her: det finnes ingen ``BL``. Et signal
    kan flytte en oppgave oppover i kostnad eller kreve en designrunde. Ingen
    signal kan tale for den billige klassen — den nås bare ved at ingenting
    taler mot den, og at positiv evidens for reversibilitet og kontrakt er
    lagt fram.

    Dette er ikke stilistisk. Et ``Disposition.BL`` ville vært en vei for et
    enkelt-signal til å oppheve et annet, og den veien går alltid nedover i
    kostnad, fordi det er den som lønner seg for den som klassifiserer.
    """

    #: Arkitekturvedtak kreves.
    ADR = "adr"
    #: Evidensen holder ikke til å plassere oppgaven. Eskaler.
    DOUBT = "doubt"
    #: Klassen kan stå, men designet må gjennom steg 7 uansett.
    DESIGN_REVIEW = "design_review"


class Signal(str, Enum):
    """Falsifiserbare signaler. Hvert treff bærer med seg hva som utløste det."""

    TRUST_BOUNDARY = "trust_boundary"
    AUTONOMY_BOUNDARY = "autonomy_boundary"
    HARD_LIMIT = "hard_limit"
    NEW_REGISTER = "new_register"
    CROSS_SURFACE_CONTRACT = "cross_surface_contract"
    BLAST_RADIUS = "blast_radius"
    IRREVERSIBLE = "irreversible"
    UNKNOWN_REVERSIBILITY = "unknown_reversibility"
    MISSING_CONTRACT_REF = "missing_contract_ref"
    UNDECLARED_BOUNDARY = "undeclared_boundary"
    TEXT_STRUCTURE_DISAGREEMENT = "text_structure_disagreement"
    EMPTY_PROPOSAL = "empty_proposal"


class Reversibility(str, Enum):
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    #: Default. Ikke «antagelig reversibel» — ukjent. Se
    #: ``LandingScopeGate``: fravær av data er ikke et positivt funn.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SignalHit:
    """Ett signal som fyrte, med det som fikk det til å fyre.

    ``evidence`` er det faktiske funnet — ordet, stien, tallet — ikke en
    gjenfortelling av det. En begrunnelse man ikke kan etterprøve er en
    påstand, og påstander er det denne modulen finnes for å begrense.
    """

    signal: Signal
    disposition: Disposition
    evidence: str
    #: ``"declared"`` (proposeren skrev det) · ``"text"`` (forespørselens
    #: ordlyd) · ``"measured"`` (stier, diff, tall). Kilden avgjør hvem som
    #: blir overprøvd når to er uenige.
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "signal": self.signal.value,
            "disposition": self.disposition.value,
            "evidence": self.evidence,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Leksikalske detektorer.
#
# Listene er bevisst KORTE og høy-presisjon. Et støyende leksikalsk lag som
# fyrer på alt gjør ``ADR`` til standardklassen — den MOTSATTE feilen av den
# modulen er bygget mot, ikke en trygg versjon av den. Ord som «gate»,
# «schema» og «protocol» er utelatt nettopp fordi de er overalt i dette
# repoet: de skiller ikke.
#
# ORDGRENSER, OG HVORFOR DE IKKE ER KOSMETIKK
# --------------------------------------------
# Første utkast brukte ``term in haystack``. Reviewer målte hva det koster:
#
#     "doi"      fyrte på  «we are DOing thIs today»   -> hard-limit -> ADR
#     "counter"  fyrte på  «the scheduler ENCOUNTERs»  -> nytt register -> ADR
#     "eierskap" fyrte på  «EierskapPage»              -> tillitsgrense -> ADR
#
# Tre helt ordinære setninger, tre arkitekturvedtak. Termene matches derfor med
# ordgrense i begge ender. Et term som SKAL tåle suffiks skrives med ``*``:
# ``"autonom*"`` dekker autonom/autonomi/autonomy/autonomous, mens ``"doi"``
# uten stjerne aldri kan treffe «doing».
#
# ``eierskap``/``ownership`` er strøket helt — de er substantiv om et helt
# alminnelig tema, og intensjonen Morten navnga («hvem eier hva») bæres
# allerede av frasene ``hvem eier``/``who owns``.
#
# Skanner tittel + beskrivelse — forespørselens ordlyd. Diff og filstier har
# egne, smalere mønstre lenger nede, fordi kildekode bruker de samme ordene
# uten å bety det samme.
# ---------------------------------------------------------------------------

TRUST_TERMS: tuple[str, ...] = (
    "tillitsgrense", "trust boundary", "trust-boundary",
    "autonomi-grense", "autonomigrense", "autonomy boundary", "bounded autonomy",
    "autonom*", "selvstendig*",
    "landingsevne", "landing capability", "landingsrett",
    "uten godkjenning", "without approval", "uten mortens", "self-approve",
    "selvgodkjenn*", "rubber-stamp", "rubberstamp",
    "hvem eier", "who owns",
    "privilegi*", "privilege*", "rettighet*", "credential*", "kreditiv*",
    "ssh-nøkkel", "ssh key", "sshd*",
)
# BEVISST UTELATT fra `TRUST_TERMS`: «eskaler»/«escalate». Å eskalere er å
# RESPEKTERE en grense, ikke å flytte den, og ordet står i nesten hver
# gate-beskrivelse i dette repoet.

HARD_LIMIT_TERMS: tuple[str, ...] = (
    # Grensene ved navn. De hører hjemme HER og ikke i `TRUST_TERMS`: et treff
    # skal si hva som ble funnet, ikke bare at noe ble funnet. Første utkast
    # la dem i `TRUST_TERMS`, og regresjonstesten mot ADR-062 V5-setningen
    # falt — den fant en tillitsgrense der teksten sa «hard-limit #3».
    "hard-limit", "hard limit", "hardlimit",
    "klinisk*", "clinical*", "pasient*", "patient*", "clinical_private", "a7",
    "doi", "dois", "mint*", "publiser*", "publish*",
    "detach delete", "drop constraint", "bulk-set", "bulk set",
    "irreversib*", "destruktiv*", "destructive", "slett alt", "delete all",
    "live-infra", "live infra", "start container", "fjern container",
    "docker compose down", "systemctl", "rm -rf",
)

REGISTER_TERMS: tuple[str, ...] = (
    "nytt register", "new register", "eget register",
    "navnerom", "namespace*",
    "ny kontrakt", "new contract", "kontrakt mellom",
    "nummerserie", "id-serie", "allokator", "allocator", "counter",
    "nytt felt i grafen", "ny node-type", "new node type", "ny label",
)

CROSS_SURFACE_TERMS: tuple[str, ...] = (
    "mellom flater", "cross-surface", "på tvers av flater",
    "mellom .13 og", "mellom .15 og", "mellom hermes og", "mellom agi og",
    "ny integrasjon", "new integration", "eksponer*", "expose*",
    "api mellom", "bro mellom", "bridge between",
)


def _compile_term(term: str) -> re.Pattern[str]:
    """``"doi"`` -> helord. ``"autonom*"`` -> prefiks som tåler suffiks."""
    if term.endswith("*"):
        return re.compile(rf"\b{re.escape(term[:-1])}", re.IGNORECASE)
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


def _compiled(terms: Sequence[str]) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((t, _compile_term(t)) for t in terms)


_TERM_SETS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "trust": _compiled(TRUST_TERMS),
    "hard_limit": _compiled(HARD_LIMIT_TERMS),
    "register": _compiled(REGISTER_TERMS),
    "cross_surface": _compiled(CROSS_SURFACE_TERMS),
}

# ---------------------------------------------------------------------------
# Strukturelle detektorer: filstier og diff-innhold.
#
# Disse er `source="measured"` — de leser hva som faktisk endres, ikke hva
# noen skrev om det. En erklæring kan ikke overprøve dem.
# ---------------------------------------------------------------------------

#: Stier som per definisjon er hard-limit #3 (live infra med sideeffekter).
HARD_LIMIT_PATH_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"sshd_config", "hard-limit #3: sshd-konfig på levende vert (ADR-062 §V1b)"),
    (r"docker-compose[^/]*\.ya?ml$", "hard-limit #3: compose-topologi"),
    (r"\.service$", "hard-limit #3: systemd-enhet"),
    # `(^|/)cron/` og ikke `/cron/`: reviewer målte at `cron/suggestions.py` --
    # en fil som ligger endret i dette treet nå -- ikke traff, mens
    # `agent/cron/x.py` traff. Et falskt NEGATIV på en hard-limit feiler i feil
    # retning; det er hele grunnen til at stier leses i det hele tatt.
    (r"(^|/)cron/|crontab", "hard-limit #3: planlagt kjøring på vert"),
    (r"LaunchAgents|\.plist$", "hard-limit #3: launchd-enhet"),
    (r"authorized_keys", "hard-limit #3 + tillitsgrense: ssh-autoritet"),
)

#: Et DOI-bærende navn, med de ordgrensene som faktisk gjelder i kode.
#: ``doi``/``dois`` alene, ``doi_payload``/``doi_record`` som prefiks, og
#: ``article_doi``/``payload_doi`` som suffiks -- men ALDRI ``doing`` eller
#: ``doing_minutes``.
_DOI_TOKEN = r"(?:\bdoi(?:s\b|_\w+|\b)|\b\w+_dois?\b)"

#: Diff-innhold som er hard-limit uansett hvem som skrev det.
HARD_LIMIT_DIFF_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"DETACH\s+DELETE", "hard-limit #4: irreversibel grafsletting"),
    (r"DROP\s+CONSTRAINT", "hard-limit #4: fjerner unikhetsgaranti"),
    (r"docker\s+compose\s+(down|rm|stop)", "hard-limit #3: river live-infra"),
    (r"docker\s+(rm|stop)\s", "hard-limit #3: river live-container"),
    (r"systemctl\s+(stop|disable|mask)", "hard-limit #3: stopper live-enhet"),
    (r"rm\s+-rf\s", "hard-limit #4: irreversibel filsletting"),
    (r"CLINICAL_PRIVATE|medicine_clinical", "hard-limit #2: klinisk/A7-data"),
    # DOI-minting. Det første mønsteret (`mint[_a-z]*\s*\(.*doi|doi.*mint`) hadde
    # presisjonen snudd på hodet, målt av reviewer: `mint[_a-z]*` slukte `mint_doi`
    # og krevde så ENDA en «doi» etter parentesen, så `mint_doi(record)` og
    # `figshare.mint_doi()` gikk fri -- mens kommentaren «# DOI: never mint here»
    # fyrte. Et mønster som bommer på kallet og treffer forbudet mot kallet er en
    # kontroll som beskytter feil retning.
    # Ingen avsluttende `\b` etter `doi`/`mint`: `mint_doi_for(...)` og
    # `doi_minter(...)` fortsetter i et ordtegn, så `\b` slo dem begge ut.
    #
    # REVIEWER-FUNN N2, og en regresjon jeg selv innførte: jeg rettet nøyaktig
    # den feilen på de to første grenene og lot den stå på den tredje. Følgen
    # var at `client.mint(doi_payload)` -- som traff FØR fiksen -- ble borte,
    # sammen med `self.mint(article_doi)` og `mint(build(x), doi)` (`[^)]*`
    # stoppet på den indre parentesen). Argumentnavnet er det vanlige tilfellet.
    # `.*` i stedet for `[^)]*` overlever nøstede kall og er linjeavgrenset,
    # siden `.` ikke krysser linjeskift.
    #
    # REVIEWER-FUNN F1: `\bmint` bommer på `_mint_doi` og `figshare_mint(doi)`
    # -- understrek-prefikset er standard python-skrivemåte for en privat
    # metode, og `\b` holder ikke midt i et ord. `\w*mint` fanger begge. Det
    # er trygt fordi hver gren uansett krever DOI-nærhet: gren 1 og 2 krever
    # `doi` klistret inntil `mint`, gren 3 krever et DOI-token på linja.
    (rf"\w*mint[_a-z]*doi\w*|\bdoi[_a-z]*mint\w*|\w*mint\w*\s*\(.*{_DOI_TOKEN}",
     "hard-limit #1: DOI mintes aldri av systemet (foreslås som :DOICandidate)"),
)

#: Diff-innhold som innfører et nytt register/navnerom.
REGISTER_DIFF_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"CREATE\s+CONSTRAINT", "nytt unikhetsnavnerom i grafen"),
    (r"class\s+\w*Counter\b", "ny teller = ny nummerserie"),
    (r"def\s+allocate_\w+", "ny allokator = nytt nummerrom"),
)

#: ``re.ASCII`` er ikke pynt: uten den er ``\d`` unicode-bred, og
#: ``ADR-٠٤٧`` ble tolket som 47. ``0\d{2}|[1-9]\d{2,}`` avviser ``ADR-0047``
#: i stedet for å normalisere det til 47 -- en feilskrevet referanse skal si
#: fra, ikke bli stille rettet til en annen ADR.
_ADR_REF_RE = re.compile(r"^ADR-(0\d{2}|[1-9]\d{2,})(?:-F(\d+))?$",
                         re.IGNORECASE | re.ASCII)

#: Allokatoren, ved navn. Regelen som bare navnga BL-varianten er selve
#: årsaken til BL-3824 — så den navngis her.
ADR_ALLOCATOR_CMD = "python3 tools/allocate_adr.py"
#: Allokatoren bor i AGI-repoet på `.13`. ADR-062 §5 står fortsatt åpen:
#: den er ikke nåbar fra `.15`, og V4 flyttet avhengigheten uten å gi den et
#: hjem. Klassifisereren later ikke som noe annet.
ADR_ALLOCATOR_HOST = ".13 (AGI-repo)"


def parse_adr_ref(ref: str) -> tuple[int, int | None] | None:
    """Tolk en ADR-referanse. Returnerer ``(nummer, fase | None)``.

    Godtar både ``ADR-047`` og siteringsformen ``ADR-047-F5``. Flerhet er
    LEGITIMT: ADR-042, ADR-043 og ADR-047 bæres av to filer hver i dag, og
    ADR-047 er én beslutning i fem faser som ikke skal renummereres. Denne
    funksjonen tolker en referanse — den teller ikke filer, og har derfor
    ingen mening om hvor mange som finnes.
    """
    m = _ADR_REF_RE.match(ref.strip())
    if not m:
        return None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


#: Toppnivå-pakkene i DETTE repoet — de IMPORTERBARE, altså katalogene med
#: ``__init__.py``. Et modul-symbol må starte i en av dem.
#:
#: REVIEWER-FUNN N1: uten denne forankringen var ``^[\w]+(?:\.[\w]+)+\b`` bare
#: «inneholder et punktum», og målt kjøpte alt dette BL::
#:
#:     "n.a"   "1.0"   "no.contract"   "tbd.tbd"   "README.md"   "v1.2.3"
#:     "e.g. dette bor i eksisterende kode"      <- `\b` slutter etter «e.g»
#:
#: Baren gikk fra «en ikke-tom streng» til «en streng med punktum i». Fortsatt
#: et felt en proposer slår på første forsøk, og det er den ENESTE positive
#: evidensen som gater den billige klassen.
#:
#: Repoets egen toppnivå-struktur er et LOKALT strukturelt faktum -- den
#: gjeninnfører ikke avhengigheten til registeret på `.13`, og dermed heller
#: ikke sirkulariteten ADR-062 V4 dokumenterer.
#:
#: REVIEWER-FUNN F2: første versjon var ``ls -d */`` HÅNDNORMALISERT til
#: understrek, og normaliseringen fant opp fire modulrøtter som ikke kan
#: finnes: ``mcp``, ``optional_mcps``, ``optional_skills``, ``ui_tui`` (de
#: ekte katalogene heter ``optional-mcps``, ``optional-skills``, ``ui-tui``
#: -- med bindestrek, altså ikke importerbare i det hele tatt, og det finnes
#: ingen toppnivå-``mcp``). Feilretningen var TILLATENDE, den ene jeg ikke
#: ville ha.
#:
#: Riktig univers er ikke «kataloger» men «importerbare pakker» -- katalogen
#: har ``__init__.py``. Det er nøyaktig mengden et ``modul/symbol`` kan peke
#: inn i, og den er både mindre og skarpere.
#:
#: DRIFT: settet er en snapshot, og modulen leser bevisst ikke filsystemet ved
#: import (en sideeffektfri modul skal ikke avhenge av cwd). Vakten mot drift
#: står i TESTEN, der filsystemlesing er gratis --
#: ``test_repo_packages_matches_the_real_importable_packages``. En pakke som
#: legges til eller døpes om feiler høylytt i CI i stedet for å snevre inn
#: klassifisereren i stillhet måneder senere.
_REPO_PACKAGES: frozenset[str] = frozenset({
    "acp_adapter", "agent", "cron", "gateway", "hermes_cli",
    "plugins", "providers", "tests", "tools", "tui_gateway",
})

_MODULE_REF_RE = re.compile(r"^([A-Za-z_]\w*)(?:\.[A-Za-z_]\w*)+\b")


def _is_module_ref(text: str) -> bool:
    m = _MODULE_REF_RE.match(text)
    return bool(m) and m.group(1) in _REPO_PACKAGES


#: Formene en eksisterende kontrakt kan ha.
#:
#: REKKEFØLGEN TELLER, og gjorde det på feil måte i forrige utkast: den
#: prikk-baserte regelen sto FØRST og slukte hvert filnavn, så ``image.png``
#: ble godtatt som «modul/symbol» og hvitelisten i ``fil`` var død kode. Fil
#: prøves nå først, slik at utvidelses-hvitelisten faktisk blir konsultert.
_CONTRACT_FORMS: tuple[tuple[object, str], ...] = (
    (re.compile(r"^ADR-(?:0\d{2}|[1-9]\d{2,})(?:-F\d+)?\b", re.IGNORECASE | re.ASCII), "ADR"),
    (re.compile(r"^BL-[1-9]\d*\b", re.IGNORECASE | re.ASCII), "BL"),
    (re.compile(r"^CAD-[A-Z0-9][A-Z0-9.-]*\b", re.IGNORECASE | re.ASCII), "CAD"),
    (re.compile(r"^[\w./-]+\.(?:py|ts|tsx|js|json|ya?ml|sh)\b"), "fil"),
    (_is_module_ref, "modul/symbol"),
)


def parse_contract_ref(ref: str) -> str | None:
    """Er dette en NAVNGITT kontrakt, eller bare noe som ble skrevet i feltet?

    Returnerer formens navn (``"ADR"``, ``"BL"``, ``"CAD"``, ``"modul/symbol"``,
    ``"fil"``) eller ``None``.

    REVIEWER-FUNN, OG DET ER DET SKARPESTE I HELE REVIEWEN. Første utkast
    sjekket bare ``contract_ref.strip()``. Målt gikk alle disse rett til BL::

        "n/a"   "TBD"   "none"   "x"   "0"   "ikke relevant"

    Modulens egen docstring fordømmer nøyaktig dette to avsnitt lenger opp — et
    felt som ikke kan feile, som blir sitert som en kontroll. Jeg resonnerte
    riktig om ADR-nummeret og bygget så kvitteringsfeltet ett argument bortenfor.
    ``parse_adr_ref`` fantes, var eksportert og testet, og hadde null kallere i
    produksjon. Det er BL-3824-mønsteret i miniatyr: verktøyet fantes, ingen
    kalte det.

    Referansen matches fra STARTEN av strengen, ikke hvor som helst i den, slik
    at «n/a — se ADR-999» ikke passerer på et sitat inne i en unnskyldning.

    Denne funksjonen sjekker FORM, ikke eksistens. At ``ADR-999`` finnes er
    ``DesignGate`` (steg 7) sin jobb, med ``source_refs["adr"]`` mot det ekte
    registeret på `.13`. Å late som noe annet her ville vært den samme
    kontrollen-som-ikke-kan-feile en gang til.
    """
    text = ref.strip()
    if not text:
        return None
    for form, name in _CONTRACT_FORMS:
        matched = form(text) if callable(form) else bool(form.match(text))
        if matched:
            return name
    return None


@dataclass(frozen=True)
class TaskProposal:
    """Det steg 3 har å gå på.

    ``declared_*``-feltene er ``bool | None`` med vilje. ``None`` er ikke
    ``False``: det er «ingen erklærte noe», og det er et eget funn
    (:data:`Signal.UNDECLARED_BOUNDARY` → ``DOUBT``). Å la ``None`` bety
    ``False`` ville gitt den billige klassen gratis når ingen svarte — som er
    presis den skjevheten modulen finnes for.
    """

    title: str
    description: str = ""
    #: Filer endringen forventes å røre. Anslag på steg 3; målt på steg 8.
    touched_paths: tuple[str, ...] = ()
    #: Diff-tekst hvis den finnes. Tom på steg 3 — det er normalt, ikke et funn.
    diff_text: str = ""
    reversibility: Reversibility = Reversibility.UNKNOWN
    #: Den EKSISTERENDE kontrakten endringen bor inne i. En akseptert ADR er
    #: en gyldig kontrakt her — å implementere et allerede fattet vedtak er
    #: BL-arbeid.
    contract_ref: str = ""
    #: Rører denne en tillits- eller autonomi-grense? ``None`` = ubesvart.
    declared_trust_boundary_change: bool | None = None
    #: Innfører den et nytt register, navnerom eller kontrakt mellom flater?
    declared_new_register: bool | None = None
    #: Anslått blast-radius. Utelatt på steg 3 er normalt — diffen finnes ikke.
    estimated_changed_files: int | None = None
    estimated_changed_lines: int | None = None

    def haystack(self) -> str:
        return f"{self.title}\n{self.description}".lower()


@dataclass(frozen=True)
class MeasuredScope:
    """Faktisk målt blast-radius fra steg 8, pluss den faktiske diffen."""

    changed_files: int
    changed_lines: int
    deleted_lines: int = 0
    new_dependencies: int = 0
    touched_paths: tuple[str, ...] = ()
    diff_text: str = ""


@dataclass(frozen=True)
class Classification:
    task_class: TaskClass
    hits: tuple[SignalHit, ...]
    design_review_required: bool
    reasons: tuple[str, ...]
    next_action: str
    #: Sant når klassen er ADR: steg 7 må hente nummer fra allokatoren.
    #: Klassifisereren deler aldri ut ett selv — se modul-docstringen.
    requires_adr_allocation: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "task_class": self.task_class.value,
            "design_review_required": self.design_review_required,
            "requires_adr_allocation": self.requires_adr_allocation,
            "hits": [h.as_dict() for h in self.hits],
            "reasons": list(self.reasons),
            "next_action": self.next_action,
        }


class TaskClassifier:
    """Steg 3: hva slags oppgave er dette?

    Rekkefølgen i :meth:`classify` er ikke tilfeldig: ett ``ADR``-treff slår
    alt, deretter ``DOUBT``, og ``BL`` er det som blir igjen når ingenting
    fyrte OG positiv evidens finnes. Det er den eneste rekkefølgen der den
    billige klassen ikke kan vinne på uavgjort.
    """

    def __init__(self, budget: ScopeBudget | None = None):
        self.budget = budget or ScopeBudget()

    # -- detektorer ---------------------------------------------------------

    @staticmethod
    def _lexical(haystack: str, term_set: str, signal: Signal,
                 disposition: Disposition) -> list[SignalHit]:
        return [
            SignalHit(signal, disposition, f"ordlyd: «{term}»", "text")
            for term, rx in _TERM_SETS[term_set]
            if rx.search(haystack)
        ]

    @staticmethod
    def _path_patterns(paths: Sequence[str],
                       patterns: Sequence[tuple[str, str]],
                       signal: Signal) -> list[SignalHit]:
        hits: list[SignalHit] = []
        for p in paths:
            for rx, why in patterns:
                if re.search(rx, p, re.IGNORECASE):
                    hits.append(SignalHit(signal, Disposition.ADR,
                                          f"sti {p}: {why}", "measured"))
        return hits

    @staticmethod
    def _diff_patterns(diff: str, patterns: Sequence[tuple[str, str]],
                       signal: Signal) -> list[SignalHit]:
        hits: list[SignalHit] = []
        for rx, why in patterns:
            m = re.search(rx, diff, re.IGNORECASE)
            if m:
                hits.append(SignalHit(signal, Disposition.ADR,
                                      f"diff «{m.group(0).strip()}»: {why}", "measured"))
        return hits

    def collect(self, proposal: TaskProposal) -> tuple[SignalHit, ...]:
        """Alle signaler som fyrer, uten å felle en dom. Testbar for seg."""
        hay = proposal.haystack()
        hits: list[SignalHit] = []

        if not proposal.title.strip():
            hits.append(SignalHit(
                Signal.EMPTY_PROPOSAL, Disposition.DOUBT,
                "oppgaven har ingen tittel — en oppgave uten beskrivelse kan "
                "ikke klassifiseres, og «tom» er ikke «liten»", "declared"))

        trust_hits = self._lexical(hay, "trust", Signal.TRUST_BOUNDARY, Disposition.ADR)
        register_hits = (
            self._lexical(hay, "register", Signal.NEW_REGISTER, Disposition.ADR)
            + self._lexical(hay, "cross_surface",
                            Signal.CROSS_SURFACE_CONTRACT, Disposition.ADR)
            + self._diff_patterns(proposal.diff_text, REGISTER_DIFF_PATTERNS,
                                  Signal.NEW_REGISTER)
        )
        hits += trust_hits
        hits += register_hits
        hits += self._lexical(hay, "hard_limit", Signal.HARD_LIMIT, Disposition.ADR)
        hits += self._path_patterns(proposal.touched_paths,
                                    HARD_LIMIT_PATH_PATTERNS, Signal.HARD_LIMIT)
        hits += self._diff_patterns(proposal.diff_text, HARD_LIMIT_DIFF_PATTERNS,
                                    Signal.HARD_LIMIT)

        # Et ÆRLIG JA er et signal. Uten disse to grenene ga et sant «ja» null
        # treff -- altså BL -- mens det å la feltet stå ubesvart ga DOUBT, og
        # da lønte det seg å svare sant framfor å tie. Reviewer målte det;
        # se modul-docstringen.
        if proposal.declared_trust_boundary_change is True:
            hits.append(SignalHit(
                Signal.TRUST_BOUNDARY, Disposition.ADR,
                "proposeren erklærer selv at en tillits-/autonomi-grense flyttes",
                "declared"))
        if proposal.declared_new_register is True:
            hits.append(SignalHit(
                Signal.NEW_REGISTER, Disposition.ADR,
                "proposeren erklærer selv et nytt register/navnerom/kontrakt "
                "mellom flater", "declared"))

        # Erklæring mot ordlyd. REDUNDANT PER KONSTRUKSJON -- se
        # modul-docstringen. Beholdt fordi nektelsen er det en senere leser
        # trenger å se, ikke fordi den binder.
        if proposal.declared_trust_boundary_change is False and trust_hits:
            hits.append(SignalHit(
                Signal.TEXT_STRUCTURE_DISAGREEMENT, Disposition.ADR,
                "erklært «ingen tillitsgrense», men forespørselens egen ordlyd "
                f"sier noe annet ({trust_hits[0].evidence}) — en erklæring "
                "overprøver ikke teksten den beskriver", "declared"))
        if proposal.declared_new_register is False and register_hits:
            hits.append(SignalHit(
                Signal.TEXT_STRUCTURE_DISAGREEMENT, Disposition.ADR,
                "erklært «intet nytt register», men ordlyd/diff sier noe annet "
                f"({register_hits[0].evidence})", "declared"))

        # Erklæringen som ikke ble gitt.
        if proposal.declared_trust_boundary_change is None:
            hits.append(SignalHit(
                Signal.UNDECLARED_BOUNDARY, Disposition.DOUBT,
                "ingen erklæring om tillits-/autonomi-grense; ubesvart er ikke "
                "«nei»", "declared"))
        if proposal.declared_new_register is None:
            hits.append(SignalHit(
                Signal.UNDECLARED_BOUNDARY, Disposition.DOUBT,
                "ingen erklæring om nytt register/navnerom/kontrakt; ubesvart "
                "er ikke «nei»", "declared"))

        # Positiv evidens for den billige klassen. Fraværet er funnet.
        if proposal.reversibility is Reversibility.IRREVERSIBLE:
            hits.append(SignalHit(
                Signal.IRREVERSIBLE, Disposition.ADR,
                "endringen er erklært irreversibel", "declared"))
        elif proposal.reversibility is Reversibility.UNKNOWN:
            hits.append(SignalHit(
                Signal.UNKNOWN_REVERSIBILITY, Disposition.DOUBT,
                "reversibilitet ukjent — ukjent er ikke reversibel", "declared"))

        raw_contract = proposal.contract_ref.strip()
        if not raw_contract:
            hits.append(SignalHit(
                Signal.MISSING_CONTRACT_REF, Disposition.DOUBT,
                "ingen eksisterende kontrakt oppgitt som endringen bor inne i; "
                "«innenfor en eksisterende kontrakt» må navngi kontrakten",
                "declared"))
        elif parse_contract_ref(raw_contract) is None:
            hits.append(SignalHit(
                Signal.MISSING_CONTRACT_REF, Disposition.DOUBT,
                f"«{raw_contract}» er ikke en navngitt kontrakt (ADR-/BL-/CAD-ref, "
                "modul-symbol eller filsti) — et utfylt felt er ikke en kontrakt",
                "declared"))

        # Blast-radius ANSLAG. Fravær blokkerer ikke — diffen finnes ikke på
        # steg 3, og å kreve den her ville gjeninnført sirkulariteten i
        # ADR-062 V4.
        est_files = proposal.estimated_changed_files
        est_lines = proposal.estimated_changed_lines
        if est_files is not None or est_lines is not None:
            ok, violations = self.budget.evaluate(
                changed_files=est_files or 0,
                changed_lines=est_lines or 0,
            )
            if not ok:
                hits.append(SignalHit(
                    Signal.BLAST_RADIUS, Disposition.DESIGN_REVIEW,
                    "anslått blast-radius over ScopeBudget: " + ", ".join(violations),
                    "declared"))

        return tuple(hits)

    # -- dommen -------------------------------------------------------------

    def classify(self, proposal: TaskProposal) -> Classification:
        hits = self.collect(proposal)
        return self._verdict(hits, floor=TaskClass.BL)

    def reclassify_on_measurement(
        self,
        prior: Classification,
        proposal: TaskProposal,
        measured: MeasuredScope,
    ) -> Classification:
        """Steg 8: mat den FAKTISKE diffen tilbake. Skrallen går én vei.

        Den målte diffen kan avsløre det anslaget ikke viste — en
        ``DETACH DELETE``, en ``sshd_config``, en ny allokator. Derfor kjøres
        detektorene på nytt mot det som faktisk endres.

        Den kan ALDRI løsne. En oppgave som ble ADR på steg 3 forblir minst
        ADR selv om diffen ble liten, og en designrunde som er utløst blir
        ikke avlyst. Grunnen er den samme som hele modulen: nedgraderingen er
        den retningen som lønner seg for den som klassifiserer, og en skralle
        som kan gå begge veier er ingen skralle.
        """
        remeasured = replace(
            proposal,
            touched_paths=tuple(measured.touched_paths) or proposal.touched_paths,
            diff_text=measured.diff_text or proposal.diff_text,
        )
        hits = list(self.collect(remeasured))

        ok, violations = self.budget.evaluate(
            changed_files=measured.changed_files,
            changed_lines=measured.changed_lines,
            deleted_lines=measured.deleted_lines,
            new_dependencies=measured.new_dependencies,
        )
        if not ok:
            hits.append(SignalHit(
                Signal.BLAST_RADIUS, Disposition.DESIGN_REVIEW,
                "MÅLT blast-radius over ScopeBudget: " + ", ".join(violations),
                "measured"))

        # Skrallen: gulvet er den forrige klassen, og en utløst designrunde
        # forblir utløst.
        merged = tuple(prior.hits) + tuple(h for h in hits if h not in prior.hits)
        verdict = self._verdict(merged, floor=prior.task_class)
        if prior.design_review_required and not verdict.design_review_required:
            verdict = replace(verdict, design_review_required=True)
        return verdict

    def _verdict(self, hits: tuple[SignalHit, ...] | Sequence[SignalHit],
                 *, floor: TaskClass) -> Classification:
        hits = tuple(hits)
        adr = [h for h in hits if h.disposition is Disposition.ADR]
        doubt = [h for h in hits if h.disposition is Disposition.DOUBT]
        design = [h for h in hits if h.disposition is Disposition.DESIGN_REVIEW]

        if adr:
            task_class = TaskClass.ADR
            driving = adr
        elif doubt:
            task_class = TaskClass.DOUBT
            driving = doubt
        else:
            task_class = TaskClass.BL
            driving = design

        # Skrallen. `max` på indeks, ikke på verdi — enum-rekkefølgen er
        # kostnadsrekkefølgen, og den er eksplisitt i `_CLASS_ORDER`.
        if _CLASS_ORDER.index(task_class) < _CLASS_ORDER.index(floor):
            task_class = floor
            driving = driving or list(hits)

        design_review_required = bool(design) or task_class is not TaskClass.BL

        if task_class is TaskClass.ADR:
            next_action = (
                f"skriv ADR-en FØRST. Nummer hentes fra allokatoren, aldri for "
                f"hånd: `{ADR_ALLOCATOR_CMD}` på {ADR_ALLOCATOR_HOST}. "
                "Designet vurderes deretter av en uavhengig vurderer "
                "(Claude Opus via Anthropic-API i Hermes GUI :9119) før steg 8."
            )
        elif task_class is TaskClass.DOUBT:
            next_action = (
                "IKKE bygg. Evidensen holder ikke til å plassere oppgaven, og "
                "tvil løses ikke til BL fordi BL er billigere. Skaff det som "
                "mangler (se reasons) eller eskaler til en uavhengig vurdering "
                "av klassifiseringen selv."
            )
        elif design_review_required:
            next_action = (
                "BL, men blast-radius krever designrunde på steg 7 før bygging."
            )
        else:
            next_action = "BL: fortsett til steg 4 (pre_rails) og steg 5 (bl_gate)."

        reasons = tuple(h.evidence for h in driving) or (
            "ingen signal fyrte, og positiv evidens for reversibilitet og "
            "kontrakt er lagt fram",
        )
        return Classification(
            task_class=task_class,
            hits=hits,
            design_review_required=design_review_required,
            reasons=reasons,
            next_action=next_action,
            requires_adr_allocation=task_class is TaskClass.ADR,
        )


# ---------------------------------------------------------------------------
# Uavhengig designvurdering.
#
# Mortens direktiv: designet gjøres av Hermes; REVIEW AV DESIGNET gjøres av
# Claude Opus via API i Hermes GUI (.15:9119) — IKKE cortex på .13.
#
# Poenget er ikke hvilken modell som er best. Poenget er at vurdereren ikke
# skal være den samme intelligensen som forfattet designet. Hermes' substrat
# er den lokale cortexen (LM Studio, `.13`, ADR-043); en «vurdering» derfra er
# forfatteren som leser seg selv.
# ---------------------------------------------------------------------------

def assert_independent_reviewer(*, provenance: str, model: str) -> tuple[bool, str]:
    """Er dette faktisk en UAVHENGIG vurderer? Delegerer — eier ingen regel selv.

    DENNE FUNKSJONEN VAR EN EGEN IMPLEMENTASJON DA JEG SKREV DEN, og det var
    feil. Mens dette arbeidet pågikk landet BL-4055 (``d6c7eb148``) med
    :func:`agent.second_opinion.assert_independent` — provenance + streng
    Opus-modell-ID — og en verts-sjekk i
    ``second_opinion_client._independent_base_url`` som bruker
    ``urlsplit().hostname`` og dermed fanger både lookalike-verter
    (``api.anthropic.com.cortex.lan``) og ``api.anthropic.com@192.168.40.13``.

    Det dekker det min gjorde. To uavhengighets-sjekker med ulike signaturer
    og ulike feiltekster i samme tre er nøyaktig den divergensen banneret
    øverst i ``code_workflow.py`` dokumenterer — og som jeg selv brukte som
    argument for å bygge en Protocol i stedet for enda en HTTP-klient. Å så
    bygge regelen på nytt ett argument bortenfor er samme feil.

    Så: BL-4055 eier regelen. Denne er en tynn videreformidling, slik at
    klassifiserer-siden har et kallested uten å ha en mening.

    ÉN TING MIN VERSJON FANGET SOM BL-4055 IKKE GJØR, rapportert framfor
    beholdt som rivaliserende kode: ``_independent_base_url`` sjekker verten,
    ikke SKJEMAET, så en env-overstyring til ``http://api.anthropic.com``
    passerer og sender API-nøkkelen i klartekst. Fiksen hører hjemme i deres
    fil, ikke i en andre kopi her.
    """
    from agent.second_opinion import assert_independent

    reason = assert_independent(provenance=provenance, model=model)
    return not reason, reason


@dataclass(frozen=True)
class DesignReviewRequest:
    """Det som sendes til den uavhengige vurdereren.

    Klassifiseringen er MED, inkludert signalene som fyrte. Vurdereren skal
    kunne overprøve selve klassifiseringen — det er halve poenget med å ha en
    uavhengig vurderer i det hele tatt.
    """

    proposal: TaskProposal
    classification: Classification
    design_text: str = ""
    context: Mapping[str, str] = field(default_factory=dict)


class IndependentDesignReviewer(Protocol):
    """Sømmen mot vurdereren.

    Bevisst en Protocol og ikke en implementasjon: HTTP-klienten mot
    Anthropic-API-et bygges av BL-4055 (``agent/second_opinion_client.py``),
    og å bygge en nummer to her ville gitt to divergerende kopier — nøyaktig
    defekten banneret øverst i ``code_workflow.py`` dokumenterer for den fila.
    """

    def review(self, request: DesignReviewRequest) -> "DesignReviewOutcome": ...


@dataclass(frozen=True)
class DesignReviewOutcome:
    verdict: str
    reasons: tuple[str, ...] = ()
    #: Provenance-strengen vurdereren attesterte seg med, slik
    #: :func:`assert_independent_reviewer` mottok den.
    reviewer_provenance: str = ""
    #: Vurdereren kan overprøve klassifiseringen. Bare oppover — se
    #: :meth:`TaskClassifier.reclassify_on_measurement` for samme regel.
    reclassified_as: TaskClass | None = None


class UnavailableReviewer:
    """Standardvurdereren når ingen er koblet til: ESCALATE, aldri PASS.

    En manglende vurderer er ikke en bestått vurdering. Dette er den samme
    regelen som ``LandingScopeGate`` (tomt landingssett blokkerer) og
    ``RuntimeSmokeGate`` (en røyktest uten svar er ikke bestått), og den er
    her fordi standardverdien er det folk faktisk får.
    """

    def __init__(self, reason: str = "ingen uavhengig vurderer er koblet til"):
        self.reason = reason

    def review(self, request: DesignReviewRequest) -> DesignReviewOutcome:
        return DesignReviewOutcome(
            verdict="ESCALATE",
            reasons=(
                f"{self.reason} — designvurdering er ikke utført. "
                "Ikke-utført er ikke bestått.",
            ),
        )
