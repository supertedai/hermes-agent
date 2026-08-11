# BL-4055: transporten for second opinion -- Claude Opus via Anthropic API.
"""Henter en UAVHENGIG vurdering fra Claude Opus, fail-closed hele veien.

Politikken (utloeser, uenighet, normalisering) ligger i
:mod:`agent.second_opinion`. Her ligger bare tre ting: noekkelen, kallet og
tidsgrensen -- og alle tre feiler til
:meth:`~agent.second_opinion.SecondOpinionOutcome.unavailable`, som BLOKKERER.

=========================================================================
API-NOEKKELEN: 0600 + EIER-SJEKK, ALDRI HARDKODET, ALDRI FRA ENV
=========================================================================

Moensteret er ``apis/unified_api/routers/surface_receipt.py::_configured_tokens``
paa ``.13``: fila maa vaere 0600, og feil modus behandles som INGEN
konfigurasjon -- ikke som «bruk den likevel». En hemmelighet som er lesbar for
andre er ingen hemmelighet, og en tjeneste som leser den likevel gjoer en
feilkonfigurasjon til en stille aksept.

EIER-SJEKKEN er lagt til her, og ``faber_observe._resolve_lease_clear`` er
grunnen til at den maa vaere det:

    «En verifisering kan ikke avhenge av et kreditiv den verifiserte parten
    kontrollerer, og maa aldri feile aapent til dens paastand.»

Der var hullet at produsenten kunne ``chmod 0644`` token-fila og faa
verifiseringen til aa falle tilbake paa sin egen paastand. En modus-sjekk ALENE
har samme form: den spoer om filas rettigheter, ikke hvem som satte dem, saa en
fil en annen bruker eier og har chmod-et til 0600 bestaar den fint -- og da
leser vi et kreditiv vi ikke vet hvor kom fra, mot et endepunkt vi ikke valgte.
Derfor kreves ogsaa ``st_uid == geteuid()`` (eller root).

**AERLIG OM HVA DETTE IKKE LOESER.** Faber og dashboardet kjoerer BEGGE som
``agent`` paa ``.15``. Samme uid betyr at produsenten faktisk KAN slette eller
chmod-e denne fila. Det er ikke en tillitsgrense eier-sjekken kan lukke -- og
derfor er det ikke der forsvaret ligger. Forsvaret er at aa oedelegge noekkelen
ikke gir en PASS: det gir ``UNAVAILABLE``, som blokkerer. Den billigste
bryteren for aa «skru av» andre-meningen stopper altsaa kjeden i stedet for aa
aapne den. Det er hele grunnen til at fail-closed maa staa foer noekkelhaandtering
i prioritet.

Env-variabel for selve NOEKKELEN er bevisst ikke stoettet: en env-var er enda
lettere for produsent-prosessen aa sette enn en fil er aa endre, saa en
env-fallback ville gjenopprettet nettopp fallback-hullet ADR-062 stengte. Bare
STIEN kan overstyres (``SECOND_OPINION_API_KEY_FILE``), slik at modus- og
eier-sjekken alltid kjoerer paa det som faktisk leses.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from agent.second_opinion import (
    INDEPENDENT_PROVENANCE,
    ChangeUnderReview,
    SecondOpinionOutcome,
    normalise_reply,
)

#: Fila med API-noekkelen. Bare STIEN kan overstyres -- se modul-docstringen.
KEY_FILE_ENV = "SECOND_OPINION_API_KEY_FILE"
DEFAULT_KEY_FILE = "/home/agent/.secrets/second_opinion_anthropic_key"

#: Mortens direktiv, kodet: Claude Opus via Anthropic API. Ikke cortex paa
#: .13:1234 -- se `assert_independent`.
MODEL = os.environ.get("SECOND_OPINION_MODEL", "claude-opus-5")
_API_HOST = "api.anthropic.com"
#: Sendes EKSPLISITT til klienten, slik at ``ANTHROPIC_BASE_URL`` aldri faar
#: bestemme hvor andre-meningen hentes fra. Se `_independent_base_url`.
_API_BASE_URL = "https://api.anthropic.com"

#: Tidsgrense OG maks lengde. Begge er fail-closed-grenser: et kall uten
#: tidsgrense kan henge kjeden i stedet for aa blokkere den, og en diff ingen
#: kan lese i sin helhet gir en vurdering som ikke betyr det den ser ut til.
TIMEOUT_SECONDS = 120.0
MAX_REVIEW_CHARS = 60000
MAX_TOKENS = 8000

_SYSTEM = """You are an INDEPENDENT second reviewer in a governed code-landing chain.
A first reviewer has already passed this change. Your job is NOT to agree with it.
You have no stake in the change landing. Do not edit files, run commands, or act.

Assume the first reviewer may be confidently wrong. Look for what a reviewer who
already decided PASS would stop looking for: unhandled failure paths, a control
that cannot fire, a check that passes vacuously, scope beyond the stated BL,
evidence asserted rather than measured.

Return JSON ONLY, no prose, no code fences, with keys:
  status      one of "CONCUR", "DISSENT", "ESCALATE"
  reason      one sentence; REQUIRED unless status is CONCUR
  findings    array of short strings (may be empty)
  confidence  number between 0 and 1

CONCUR  = you independently reach the same PASS.
DISSENT = you would not land this. State why in `reason`.
ESCALATE = the call is a human's to make (policy, scope, or owner decision).

Do not answer CONCUR because the change looks conventional or because the first
reviewer passed it. CONCUR means you checked and found nothing. If you cannot
tell from the evidence supplied, that is DISSENT with a reason naming what is
missing — not CONCUR."""


def _env_float(name: str, default: float, *, low: float, high: float) -> float:
    """Les en tallgrense fra env, klemt til et lovlig intervall.

    Reviewer-funn 6: ``float(os.environ[...])`` paa modulnivaa lot en skrivefeil
    i env-en kaste ``ValueError`` under IMPORT. Naar ``code_workflow`` senere
    importerer denne modulen for aa haandheve steget, ville en typo tatt ned
    hele runneren -- en feilkonfigurasjon som slaar ut mer enn kontrollen den
    gjelder. At vi faller tilbake i stillhet er forsvarlig HER, og bare her:
    verdien er en tidsgrense, og BEGGE ytterpunkter feiler lukket (for kort ->
    timeout -> UNAVAILABLE; for lang -> klemt til `high`). Den kan altsaa ikke
    aapne et hull, bare bruke tid.
    """
    try:
        value = float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        value = default
    return min(max(value, low), high)


def _independent_base_url() -> str:
    """``""`` naar env peker et annet sted enn Anthropic, ellers begrunnelsen.

    Reviewer BLOCK 1, maalt: den gamle sjekken var ``_API_HOST not in base_url``
    -- en DELSTRENG-test, ikke en vertstest. Begge disse bestod den, og begge
    ga en bestaatt CONCUR:

        https://api.anthropic.com.cortex.lan/v1     (lookalike-vert)
        http://192.168.40.13:1234/#api.anthropic.com  (verten ADR-en utelukker)

    Den foerste er en sannsynlig FEILKONFIGURASJON, ikke bare et angrep. En
    vertsidentitet maa parses, ikke soekes etter i en streng.
    """
    raw = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
    if not raw:
        return ""
    host = (urlsplit(raw).hostname or "").lower()
    if host != _API_HOST:
        return (f"ANTHROPIC_BASE_URL resolves to host {host or raw!r}, not "
                f"{_API_HOST} — a model asking itself is not a second opinion")
    return ""


def _read_key_file(path: Path) -> tuple[str, str]:
    """``(noekkel, "")`` eller ``("", grunn)``. Se modul-docstringen for HVORFOR."""
    try:
        if not path.exists():
            return "", f"API key file {path} does not exist"
        stat = path.stat()
    except OSError as exc:
        return "", f"API key file {path} is unreadable: {type(exc).__name__}"

    mode = stat.st_mode & 0o777
    if mode & 0o077:
        # Feil modus = INGEN konfigurasjon, aldri «bruk den likevel».
        return "", (f"API key file {path} has mode {mode:04o}; must be 0600 — a secret "
                    "readable by others is not a secret")

    euid = os.geteuid()
    if stat.st_uid not in (euid, 0):
        return "", (f"API key file {path} is owned by uid {stat.st_uid}, not {euid} — "
                    "a credential planted by another party is not ours to trust")

    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return "", f"API key file {path} could not be read: {type(exc).__name__}"
    if not key:
        return "", f"API key file {path} is empty"
    return key, ""


def _extract_json(text: str) -> Mapping[str, Any] | None:
    """Samme kontrakt som ``faber_live_adapter._json``: ingen JSON -> None -> BLOCK."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _render_request(change: ChangeUnderReview, *, trigger_reasons: tuple[str, ...],
                    diff_text: str) -> str:
    landing = ", ".join(change.landing_set[:40]) or "(unknown)"
    return (
        f"BL: {change.bl_ref or '(none recorded)'}\n"
        f"diff_id: {change.diff_id}\n"
        f"first reviewer: {change.reviewer} -> {change.verdict} "
        f"(confidence: {change.confidence if change.confidence is not None else 'UNMEASURED'})\n"
        f"blast radius: {change.changed_files} files / {change.changed_lines} lines\n"
        f"landing set: {landing}\n"
        f"why you were called: {', '.join(trigger_reasons) or '(unspecified)'}\n"
        f"change summary: {change.summary or '(none supplied)'}\n\n"
        f"--- diff ---\n{diff_text}\n--- end diff ---"
    )


def fetch_second_opinion(change: ChangeUnderReview, *,
                         trigger_reasons: tuple[str, ...] = (),
                         diff_text: str = "",
                         key_file: str | os.PathLike[str] | None = None,
                         model: str = MODEL) -> SecondOpinionOutcome:
    """Kall Claude Opus. ENHVER feil gir ``UNAVAILABLE``, som blokkerer.

    Merk at det ikke finnes en ``except`` som ender i noe annet enn
    ``unavailable``. Det er tilsiktet: en bred ``except`` som returnerte
    «antagelig greit» ville vaert nettopp den kontrollen som ikke kan fyre.
    """
    path = Path(key_file or os.environ.get(KEY_FILE_ENV) or DEFAULT_KEY_FILE)
    key, reason = _read_key_file(path)
    if not key:
        return SecondOpinionOutcome.unavailable(reason, gate="second_opinion_credential")

    # UAVHENGIGHET, mekanisk. To lag, fordi ett ikke holdt:
    #   1) env-en avvises hvis den peker paa en annen VERT (parset, ikke soekt),
    #   2) base_url sendes uansett EKSPLISITT under, saa env-en ikke kan velge
    #      endepunkt selv om sjekken en dag skulle svikte.
    drift = _independent_base_url()
    if drift:
        return SecondOpinionOutcome.unavailable(
            drift, gate="second_opinion_independence")

    if not diff_text.strip():
        # Tomt diff = ingenting aa vurdere. Ikke «ingen innvendinger».
        return SecondOpinionOutcome.unavailable(
            "no diff text was supplied to review — an unreviewed change is not an "
            "approved one", gate="second_opinion_input")
    if len(diff_text) > MAX_REVIEW_CHARS:
        return SecondOpinionOutcome.unavailable(
            f"diff exceeds bounded review size ({len(diff_text)} > {MAX_REVIEW_CHARS} "
            "chars); a reviewer that cannot see the whole change cannot pass it",
            gate="second_opinion_input")

    try:
        import anthropic
    except Exception as exc:  # noqa: BLE001
        return SecondOpinionOutcome.unavailable(
            f"anthropic SDK unavailable: {type(exc).__name__}",
            gate="second_opinion_runtime")

    try:
        client = anthropic.Anthropic(
            api_key=key,
            # EKSPLISITT: uten dette leser SDK-en ANTHROPIC_BASE_URL selv, og
            # da avgjoer miljoeet hvem som er «den uavhengige vurdereren».
            base_url=_API_BASE_URL,
            timeout=_env_float("SECOND_OPINION_TIMEOUT", TIMEOUT_SECONDS,
                               low=5.0, high=600.0),
            max_retries=1,
        )
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": _render_request(change, trigger_reasons=trigger_reasons,
                                           diff_text=diff_text),
            }],
        )
    except Exception as exc:  # noqa: BLE001
        # Timeout, 401, 429, 5xx, nettverk -- alle samme sted: ikke bestaatt.
        return SecondOpinionOutcome.unavailable(
            f"API call failed: {type(exc).__name__}", gate="second_opinion_transport")

    # Claude Opus 5 kan avslaa via sikkerhetsklassifikatorene: HTTP 200 med
    # stop_reason "refusal" og tomt/delvis innhold. Aa lese content[0] uten
    # denne sjekken ville gitt en tom parse og en misvisende grunn.
    if getattr(response, "stop_reason", None) == "refusal":
        return SecondOpinionOutcome.unavailable(
            "model declined to review this change (stop_reason=refusal)",
            gate="second_opinion_refusal")

    text = "".join(
        getattr(block, "text", "") or ""
        for block in (getattr(response, "content", None) or [])
        if getattr(block, "type", "") == "text"
    )
    if getattr(response, "stop_reason", None) == "max_tokens" and not _extract_json(text):
        return SecondOpinionOutcome.unavailable(
            "reply was truncated at max_tokens before a verdict was returned",
            gate="second_opinion_transport")

    # INGEN fallback til `model` (det vi SPURTE om). Reviewer BLOCK 1: den
    # fallbacken gjorde forespoerselen til sin egen attest -- en responder som
    # bare utelot `model` fikk vaart oenskede navn skrevet inn i sin egen
    # identitet, og bestod uavhengighetssjekken. Tomt navn -> `assert_independent`
    # avviser -> UNAVAILABLE -> blokkerer.
    return normalise_reply(_extract_json(text),
                           provenance=INDEPENDENT_PROVENANCE,
                           model=str(getattr(response, "model", "") or ""))
