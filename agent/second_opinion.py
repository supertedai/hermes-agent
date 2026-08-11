# BL-4055: SECOND OPINION -- en UAVHENGIG vurderer i steg 10.
"""Andre-mening for Fabers 13-stegs kjede: utloeser, uenighetspolitikk, fail-closed.

MAALT 2026-08-11 foer denne fila fantes: null treff paa ``second_opinion`` /
``dissent`` / ``adversarial`` i ``agent/``. De aatte treffene i repoet var
optional-skills (``dogfood/adversarial-ux-test``, en UX-testskill) og
``creative-ideation/premortem-and-inversion``. Kjeden hadde ingen andre-mening
i det hele tatt: steg 10 var én reviewer, og dens PASS var endelig.

Denne modulen er BEVISST uten sideeffekter og uten nettverk -- den er ren
politikk, saa den kan testes uten en API-noekkel. Selve kallet ligger i
:mod:`agent.second_opinion_client`.

=========================================================================
DEN AVGJOERENDE DESIGNREGELEN
=========================================================================

    **En second opinion som bare paakalles naar man allerede er i tvil,
    kalles aldri naar man tar feil med selvtillit.**

Det er derfor utloeseren her IKKE er «ved behov», og derfor den ikke bare er
«lav confidence». Et sett med utloesere som utelukkende leser reviewerens egen
selvrapport, er et sett reviewer selv kan lukke ved aa vaere sikker. To av de
fem utloeserne under er derfor MONOTONE I RISIKO OG UAVHENGIGE AV SELVRAPPORTEN
(:data:`blast_radius` og :data:`governance_surface`): de fyrer selv paa en PASS
med confidence 0.99.

=========================================================================
FRAVAER AV DATA ER IKKE ET POSITIVT FUNN
=========================================================================

Samme regel som allerede staar i ``LandingScopeGate`` (tomt landingssett
blokkerer), i ``ScopeBudget``-kallet paa steg 8 (umaalt blast-radius blokkerer)
og i ``faber_observe._resolve_lease_clear`` (uverifisert lease er ikke «clear»):

* En confidence som MANGLER er ikke hoey confidence -- den er UMAALT, og umaalt
  utloeser (:data:`confidence_unmeasured`).
* Et API-kall som feiler, timer ut eller returnerer ugyldig JSON er ikke en
  bestaatt second opinion -- det er :data:`SecondOpinionStatus.UNAVAILABLE`,
  og det BLOKKERER.

=========================================================================
HVA SKJER VED UENIGHET  (ADR: docs/design/adr-second-opinion-bl4055.md)
=========================================================================

En andre mening som kan overstyres i stillhet er dekorasjon. Valget er kodet i
:func:`resolve_disagreement`, og det er ASYMMETRISK:

1. **Uenighet BLOKKERER nedover.** Reviewer PASS + second opinion DISSENT ->
   kjeden stopper. Kostnaden er asymmetrisk: aa blokkere foer landing er
   billig og reversibelt, aa lande en gal endring er ingen av delene.
2. **Enighet loefter ALDRI oppover.** En second opinion kan nedlegge veto, men
   aldri stemple. Uten den regelen blir andre-meningen en ankeinstans
   produsenten kan kjoere til den vinner -- og da maaler den viljestyrke, ikke
   kvalitet.
3. **ESCALATE gaar til Morten**, via samme ``owner_gate``-mekanikk kjeden
   allerede har. Andre-meningen bestemmer ikke selv; den kan si «dette er
   ikke mitt aa avgjoere».
4. **BEGGE STEMMER LOGGFOERES ALLTID** -- ogsaa ved enighet. Logging er ikke
   uenighetspolitikken; den er ubetinget. En enighet uten spor er ikke
   etterproevbar, og da vet man ikke om gaten kjoerte i det hele tatt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class SecondOpinionStatus(str, Enum):
    """Utfallet av andre-meningen. ``UNAVAILABLE`` er IKKE en bestaatt sjekk."""

    CONCUR = "CONCUR"
    DISSENT = "DISSENT"
    ESCALATE = "ESCALATE"
    UNAVAILABLE = "UNAVAILABLE"


#: Provenance-verdier som teller som en UAVHENGIG vurderer. Se
#: :func:`assert_independent` for hvorfor dette er en mekanisk sjekk og ikke en
#: konvensjon.
INDEPENDENT_PROVENANCE = "anthropic.api"

#: Lovlige Opus-modell-ID-er, som et STRENGT moenster og ikke et prefiks.
#: Reviewer BLOCK 1: ``startswith("claude-opus")`` godtok
#: ``claude-opus-4-1-cortexproxy`` -- altsaa nettopp en proxy foran cortex,
#: navngitt slik at den bestod uavhengighetssjekken. Et prefiks er en aapen
#: mengde; en uavhengighetssjekk maa vaere en lukket en.
#: Aksepterer ``claude-opus-5``, ``claude-opus-4-8``,
#: ``claude-opus-4-5-20251101``; avviser alt med et ikke-numerisk haleledd.
_OPUS_MODEL_RE = re.compile(r"^claude-opus-\d+(?:-\d+)*$")


@dataclass(frozen=True)
class SecondOpinionOutcome:
    """Andre-meningens svar, normalisert.

    ``status`` er det eneste feltet kjeden doemmer paa. ``reason`` er for
    mennesket som leser BLOCKen; ``raw`` bevares for journalen.
    """

    status: SecondOpinionStatus
    reason: str = ""
    gate: str = "second_opinion"
    provenance: str = ""
    model: str = ""
    confidence: float | None = None
    findings: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_pass(self) -> bool:
        """KUN ``CONCUR`` er bestaatt. Alt annet -- inkludert manglende svar."""
        return self.status is SecondOpinionStatus.CONCUR

    @classmethod
    def unavailable(cls, reason: str, *, gate: str = "second_opinion_unavailable",
                    provenance: str = "") -> "SecondOpinionOutcome":
        """Fabrikk for fail-closed.

        Finnes som en egen konstruktoer nettopp for aa gjoere det VANSKELIG aa
        skrive et utfall som bare mangler et svar og likevel ser bestaatt ut:
        det er ingen vei fra en feil til ``CONCUR``.
        """
        return cls(status=SecondOpinionStatus.UNAVAILABLE, reason=reason,
                   gate=gate, provenance=provenance)


@dataclass(frozen=True)
class ChangeUnderReview:
    """Det andre-meningen skal doemme -- uten aa importere ``code_workflow``.

    ``verdict`` er en ren streng og ikke ``ReviewVerdict``, med vilje: denne
    modulen skal kunne testes og gjenbrukes uten aa dra inn hele kjeden, og en
    sirkulaer import mellom gate og politikk er hvordan en gate ender opp med
    aa bli definert to steder.
    """

    diff_id: str
    reviewer: str
    verdict: str
    confidence: float | None = None
    changed_files: int | None = None
    changed_lines: int | None = None
    landing_set: tuple[str, ...] = ()
    bl_ref: str = ""
    summary: str = ""


@dataclass(frozen=True)
class TriggerDecision:
    """Skal andre-meningen hentes inn, og HVORFOR."""

    required: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.required


def _as_float(value: Any) -> float | None:
    """Tallverdi, eller None. ``bool`` avvises: ``True`` er ikke confidence 1.0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    # NaN sammenlignes usant mot ALT, saa `nan < terskel` er False -- en NaN
    # ville altsaa passert terskelen ved aa vaere umaalelig. Den er umaalt.
    if parsed != parsed:
        return None
    return parsed


@dataclass(frozen=True)
class SecondOpinionTrigger:
    """Naar er en reviewer-PASS IKKE tilstrekkelig?

    Merk hva som IKKE staar her: «verdict er ikke PASS». Steg 10 stopper
    allerede kjeden paa NEEDS_REVIEW/BLOCK/ESCALATE, og en andre mening kan
    per :func:`resolve_disagreement` uansett aldri loefte en BLOCK til en
    PASS. Aa liste den som utloeser ville gitt en utloeser med null
    kallesteder -- akkurat defekten (``ScopeBudget`` og ``BlGate`` foer
    BL-4029) som hele denne kjeden holder paa aa rydde opp i.

    Utloeserne er derfor definert som: de tilfellene der kjeden ELLERS ville
    sluppet endringen gjennom.
    """

    #: Under denne verdien er reviewerens PASS ikke sterk nok til aa staa alene.
    min_confidence: float = 0.80
    #: Blast-radius-terskler. Bevisst rundt halvparten av ``ScopeBudget``s
    #: grenser (10 filer / 500 linjer): en endring trenger ikke sprenge
    #: budsjettet for aa vaere for stor til at én leser kan se hele den.
    max_changed_files: int = 5
    max_changed_lines: int = 200
    #: Selve vaktmaskineriet. En endring HER er der en selvsikker feil koster
    #: mest, fordi den svekker alle senere doemmekraft-sjekker samtidig.
    #: Reviewer-funn 4: listen var for kort. Den utelot lease-autoriteten,
    #: landings-eksekutoren, reviewer-adapteren og gatens EGEN HTTP-flate --
    #: altsaa flere av de stedene en selvsikker feil ville vaert dyrest. T5 er
    #: en av de to utloeserne som skal fange «selvsikker og gal»; da maa den
    #: daekke maskineriet, ikke bare denne ene fila.
    governance_paths: tuple[str, ...] = (
        "agent/code_workflow.py",
        "agent/faber_observe.py",
        "agent/faber_coding_ingress.py",
        "agent/faber_control_bridge.py",
        "agent/faber_goal_state.py",
        "agent/faber_implementer.py",
        "agent/faber_landing.py",
        "agent/faber_live_adapter.py",
        "agent/faber_postcommit_adapters.py",
        "agent/faber_runtime.py",
        "agent/lease_authority.py",
        "agent/second_opinion.py",
        "agent/second_opinion_client.py",
        "hermes_cli/web_server.py",
    )

    def evaluate(self, change: ChangeUnderReview) -> TriggerDecision:
        reasons: list[str] = []

        confidence = _as_float(change.confidence)
        if confidence is None:
            # UMAALT ER IKKE HOEYT. Reviewer-kontrakten i faber_live_adapter
            # har `confidence` i JSON-en; en reviewer som utelater den har ikke
            # dermed uttrykt sikkerhet.
            reasons.append("confidence_unmeasured")
        elif confidence < self.min_confidence:
            reasons.append(f"confidence_below_{self.min_confidence:g}:{confidence:g}")

        # --- De to selvrapport-UAVHENGIGE utloeserne -----------------------
        files = change.changed_files
        lines = change.changed_lines
        if files is None or lines is None:
            reasons.append("blast_radius_unmeasured")
        else:
            if files >= self.max_changed_files:
                reasons.append(f"blast_radius_files>={self.max_changed_files}:{files}")
            if lines >= self.max_changed_lines:
                reasons.append(f"blast_radius_lines>={self.max_changed_lines}:{lines}")

        touched = sorted(
            path for path in {str(p).strip() for p in change.landing_set if str(p).strip()}
            if any(path == g or path.endswith("/" + g) for g in self.governance_paths)
        )
        if touched:
            reasons.append("governance_surface:" + ",".join(touched[:5]))

        return TriggerDecision(required=bool(reasons), reasons=tuple(reasons))


@dataclass(frozen=True)
class Resolution:
    """Hva kjeden gjoer med de to stemmene."""

    allow: bool
    gate: str
    reason: str
    escalate_to_owner: bool = False
    #: Begge stemmer, alltid -- ogsaa naar de er enige.
    votes: Mapping[str, str] = field(default_factory=dict)


def resolve_disagreement(*, change: ChangeUnderReview,
                         opinion: SecondOpinionOutcome) -> Resolution:
    """Uenighetspolitikken, kodet. Se modul-docstringen for begrunnelsen.

    Funksjonen er TOTAL: hver kombinasjon av reviewer-verdikt og andre-mening
    har et definert utfall. Et hull her ville vaert et sted der uenighet
    forsvinner i stillhet, som er nettopp den defekten ADR-en beskriver.
    """
    votes = {
        "reviewer": f"{change.reviewer or 'unknown'}:{change.verdict}"
                    + (f"@{_as_float(change.confidence):g}"
                       if _as_float(change.confidence) is not None else "@unmeasured"),
        "second_opinion": f"{opinion.provenance or 'unknown'}:{opinion.status.value}"
                          + (f"@{opinion.confidence:g}"
                             if opinion.confidence is not None else "@unmeasured"),
    }

    if opinion.status is SecondOpinionStatus.UNAVAILABLE:
        return Resolution(
            allow=False,
            gate="second_opinion_unavailable",
            reason=("second opinion produced no usable verdict "
                    f"({opinion.reason or 'no reason given'}) — absence of an answer "
                    "is not a passed review"),
            votes=votes,
        )

    if opinion.status is SecondOpinionStatus.ESCALATE:
        return Resolution(
            allow=False,
            gate="second_opinion_escalate",
            reason=("second opinion declined to decide and escalated to the owner: "
                    + (opinion.reason or "no reason given")),
            escalate_to_owner=True,
            votes=votes,
        )

    if opinion.status is SecondOpinionStatus.DISSENT:
        return Resolution(
            allow=False,
            gate="second_opinion_dissent",
            reason=("independent second opinion dissents from the reviewer PASS: "
                    + (opinion.reason or "no reason given")),
            votes=votes,
        )

    # CONCUR. Reviewer BLOCK 2: uavhengighet ble tidligere bare sjekket i
    # `normalise_reply`. Det holdt saa lenge den var eneste konstruktoer -- men
    # en gate som stoler paa at ingen andre lager dens input, er en gate hvis
    # forutsetning ligger utenfor den selv. Den som bestemmer landing maa
    # haandheve sin egen forutsetning.
    independence = assert_independent(provenance=opinion.provenance,
                                      model=opinion.model)
    if independence:
        return Resolution(
            allow=False,
            gate="second_opinion_independence",
            reason=independence,
            votes=votes,
        )

    # Men enighet loefter ALDRI en ikke-PASS til en PASS.
    if str(change.verdict).upper() != "PASS":
        return Resolution(
            allow=False,
            gate="second_opinion_cannot_upgrade",
            reason=(f"reviewer verdict is {change.verdict}; a second opinion can veto "
                    "a PASS but never overturn a BLOCK"),
            votes=votes,
        )

    return Resolution(
        allow=True,
        gate="second_opinion",
        reason="reviewer and independent second opinion concur",
        votes=votes,
    )


def assert_independent(*, provenance: str, model: str) -> str:
    """Er dette faktisk en ANNEN vurderer? Tom streng = ja, ellers begrunnelse.

    **En modell som spoer seg selv er ikke en andre mening.** Mortens direktiv
    var eksplisitt: cortex-modellen paa ``.13:1234`` diskvalifiserer seg selv
    som andre-mening, uansett hvor god den er, fordi uavhengighet er hele
    poenget. Det er en mekanisk sjekk og ikke en konvensjon av samme grunn som
    ``ScopeBudget`` maatte faa et kallested: en regel ingen spoer om, er ikke
    en regel.
    """
    if provenance != INDEPENDENT_PROVENANCE:
        return (f"second opinion came from {provenance!r}, not {INDEPENDENT_PROVENANCE!r} — "
                "a reviewer that is not independent is not a second opinion")
    if not model:
        # Reviewer BLOCK 1: klienten falt tilbake paa modellnavnet VI SPURTE OM
        # naar svaret utelot sitt eget. Da attesterte forespoerselen seg selv,
        # og enhver responder som bare lar `model` staa tomt bestod sjekken.
        # Et ubesvart «hvem er du» er ikke et svar.
        return ("second opinion did not name the model that produced it; an "
                "unattested responder cannot be shown to be independent")
    if not _OPUS_MODEL_RE.match(str(model)):
        return (f"second opinion model {model!r} is not a Claude Opus model id; the "
                "independent-reviewer contract names it explicitly")
    return ""


def normalise_reply(payload: Mapping[str, Any] | None, *, provenance: str,
                    model: str) -> SecondOpinionOutcome:
    """Modellens JSON -> :class:`SecondOpinionOutcome`, fail-closed hele veien.

    Hver avvisning har SIN EGEN begrunnelse. Det er ikke pedanteri: «ingen
    JSON», «ukjent status» og «ikke uavhengig» krever helt ulike inngrep, og en
    felles «second opinion failed» ville gjort dem umulige aa skille i
    journalen.
    """
    if not isinstance(payload, Mapping):
        return SecondOpinionOutcome.unavailable(
            "reply was not a JSON object", gate="second_opinion_parse",
            provenance=provenance)

    independence = assert_independent(provenance=provenance, model=model)
    if independence:
        return SecondOpinionOutcome.unavailable(
            independence, gate="second_opinion_independence", provenance=provenance)

    raw_status = str(payload.get("status", "")).strip().upper()
    try:
        status = SecondOpinionStatus(raw_status)
    except ValueError:
        return SecondOpinionOutcome.unavailable(
            f"reply carried no recognised status (got {raw_status or 'nothing'!r}); "
            "expected CONCUR, DISSENT or ESCALATE",
            gate="second_opinion_parse", provenance=provenance)

    if status is SecondOpinionStatus.UNAVAILABLE:
        # Vurdereren faar ikke erklaere seg selv utilgjengelig og dermed
        # unnslippe et standpunkt; det er ikke en av de tre lovlige svarene.
        return SecondOpinionOutcome.unavailable(
            "reply claimed UNAVAILABLE, which is a transport outcome and not a verdict",
            gate="second_opinion_parse", provenance=provenance)

    findings = payload.get("findings")
    if isinstance(findings, str):
        findings = [findings]
    if not isinstance(findings, Sequence) or isinstance(findings, (bytes, bytearray)):
        findings = []

    reason = str(payload.get("reason", "")).strip()
    if status is SecondOpinionStatus.DISSENT and not reason and not findings:
        # En DISSENT uten begrunnelse er ikke etterproevbar, og en gate som
        # blokkerer uten aa kunne si hvorfor er umulig aa svare paa.
        #
        # Reviewer-funn 5: dette gjaldt foer ogsaa ESCALATE, som gjorde at en
        # begrunnelsesloes «dette er en menneskelig avgjoerelse» ble skrevet om
        # til «vi fikk ikke svar». Begge blokkerer, men bare den ene naar
        # Morten -- saa omskrivingen tapte nettopp det signalet som skulle
        # eskaleres. En ESCALATE uten prosa er fortsatt en ESCALATE; mennesket
        # som ser paa den, ser uansett selv.
        return SecondOpinionOutcome.unavailable(
            f"{status.value} carried neither a reason nor any findings",
            gate="second_opinion_parse", provenance=provenance)

    return SecondOpinionOutcome(
        status=status,
        reason=reason or "; ".join(str(f) for f in findings[:3]),
        provenance=provenance,
        model=model,
        confidence=_as_float(payload.get("confidence")),
        findings=tuple(str(f) for f in findings[:20]),
        raw=dict(payload),
    )
