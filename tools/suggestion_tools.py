"""hermes_suggestion_tools — Hermes' NATIVE forslags-verktøy (BL-3266).

Deployeres til `.15:/home/agent/agent-layer/hermes-agent/tools/suggestion_tools.py` og
auto-oppdages av `tools/registry.discover_builtin_tools` (toppnivå `registry.register`-kall).
Kun stdlib. Samme mønster og samme `symbiose`-toolset som `flyby_tools.py` (BL-3255/ADR-035) —
og samme grunn til å være en NY fil: `symbiose_tools.py` finnes kun på .15 og er en annen
strøms flate.

HULLET DEN LUKKER (målt 2026-08-01, diagnose learningstitch_58904 / kandidat
candidate_suggestion_surface_has_no_caller_2026_08_01)
------------------------------------------------------------------------------
`/chat/quantum-leap/suggestions` (BL-2652) transisjonerer pending→surfaced når den KALLES —
men Hermes-chatten hentet aldri forslag (OpenWebUI pensjonert), så flaten hadde i praksis
ingen kaller: 28 surfaced totalt, 8/uke via chat-veien. Ferske, MERGE-dedupede forslag
(post-BL-2652, bærer `dedup_key`) døde av TTL usett. Samme klasse som flyby `/pending` før
BL-3255: riktig rørlegging, ingen konsument. Disse to verktøyene er konsumenten.

KONTRAKTEN, som er semantikk og ikke pynt:
  * Å HENTE ER Å SURFACE. Serveren stempler det den returnerer pending→surfaced
    (chat.py BL-2652, matchet på dedup_key). `suggestions_fetch` skal derfor KUN kalles
    når forslagene faktisk VISES til Morten i svaret — aldri spekulativt med resultatet
    forkastet; det ville stemplet «vist» på ting ingen så.
  * KONSUMPSJON telles KUN ved acted/dismissed (`suggestion_feedback`) — sensor-predikatet
    er BL-2652-herdet nettopp så surfacing alene ikke kan Goodharte målingen.
  * NODE-PRODUKSJONEN er den pre-eksisterende, BUNDNE server-veien — ikke null (reviewer-
    BLOCK BL-3266 #1): `suggestions_fetch` kan persistere ≤QL_SUGGESTION_PERSIST_CAP=8
    MERGE-dedupede :ProactiveSuggestion per kall (conf-gulv 0.45, 60s server-cache;
    quantum_leap_integrator._persist_suggestion), og `suggestion_feedback` MERGEr én
    :SuggestionFeedback + justerer PREFERS_CATEGORY-vekt ±0.1. Wiringen INTRODUSERER
    ingen nye skrivere; den kaller flater som allerede skriver bundet.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from tools.registry import registry

API_BASE = os.environ.get("SYMBIOSE_API_URL", "http://192.168.40.12:8010").rstrip("/")


def _req(path: str, payload: dict | None = None, timeout: int = 30) -> str:
    """POST når payload er gitt, ellers GET. Feil returneres som JSON — en handler som
    kaster ville blitt en verktøy-feil uten diagnose i chatten (samme kontrakt som
    flyby_tools._req)."""
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"status": "error", "error": f"HTTP {e.code} fra {path}",
                           "detail": e.read()[:600].decode("utf-8", "replace")})
    except Exception as e:
        return json.dumps({"status": "error",
                           "error": f"{type(e).__name__} mot {API_BASE}{path}: {e}"})


def _suggestion_feedback(args, **kw) -> str:
    payload = {
        "user_id": str(args.get("user_id", "morten")).strip() or "morten",
        "suggestion_id": str(args.get("suggestion_id", "")).strip(),
        "suggestion_type": str(args.get("suggestion_type", "")).strip(),
        "was_accepted": bool(args.get("was_accepted")),
    }
    if not payload["suggestion_id"] or not payload["suggestion_type"]:
        # Lokal fail-closed: uten id+type matcher serverens MATCH ingenting og svarer
        # likevel ok — «feedback registrert» ville vært en usann melding. Bounces her.
        return json.dumps({"status": "error", "error": "mangler suggestion_id/suggestion_type",
                           "detail": "begge kommer fra suggestions_fetch-svaret (feltene id og type)"},
                          ensure_ascii=False)
    raw = _req("/chat/quantum-leap/feedback-v2", payload)
    # Serverens {"status":"ok"} betyr MOTTATT, ikke at en node ble truffet: null-match er
    # nåbar (forslag under conf-gulvet/forbi cap-en ble aldri persistert) og Neo4j-armen er
    # try/except-logget server-side. «Registrert på forslaget» ville vært en gjetning —
    # merk svaret så modellen ikke asserterer mer enn målt (reviewer-BLOCK BL-3266 #3).
    try:
        parsed = json.loads(raw)
        if parsed.get("status") == "ok":
            parsed["note"] = ("mottatt av serveren — IKKE bekreftelse på at noden fantes/ble "
                              "transisjonert. Si «meldt inn», ikke «registrert på forslaget»; "
                              "bekreft evt. med graph_query på suggestion_id.")
            return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        pass
    return raw


registry.register(
    name="suggestions_fetch",
    toolset="symbiose",
    schema={
        "name": "suggestions_fetch",
        "description": (
            "Hent systemets proaktive forslag (:ProactiveSuggestion-køen, quantum_leap). "
            "Bruk når Morten ber om forslag eller retning — «hva bør jeg gjøre», «noen "
            "forslag/ideer», «hva foreslår systemet», «hva venter på meg» — eller når en "
            "planleggingssamtale naturlig åpner for det. "
            "VIKTIG KONTRAKT: serveren stempler det den returnerer pending→surfaced "
            "(BL-2652) — kall KUN når du faktisk VISER forslagene til Morten i svaret, "
            "aldri spekulativt. Vis id og type per forslag; suggestion_feedback trenger dem "
            "når Morten reagerer. Å vise er ikke å konsumere — konsumpsjon telles først ved "
            "feedback (acted/dismissed), resten drenerer TTL-en selv."),
        "parameters": {"type": "object", "properties": {
            "user_id": {"type": "string", "description": "hvem forslagene gjelder (default morten)"},
        }},
    },
    # timeout 150 > serverens verste tilfelle (QL_LOCAL_TIMEOUT=120 per LLM-kall i
    # genereringen). En KLIENT-timeout under serverens ville vært verre enn treg: chat.py
    # stempler surfaced ETTER at genereringen fullfører — klipper klienten først, stemples
    # «vist» på forslag ingen så, og surfaced-målingen blåses opp av selve feilmodusen
    # kontrakten over forbyr (reviewer-BLOCK BL-3266 #2).
    handler=lambda args, **kw: _req(
        "/chat/quantum-leap/suggestions?" + urllib.parse.urlencode(
            {"user_id": str(args.get("user_id", "morten")).strip() or "morten"}),
        timeout=150),
    emoji="\U0001F4A1",
    max_result_size_chars=8000,
)

registry.register(
    name="suggestion_feedback",
    toolset="symbiose",
    schema={
        "name": "suggestion_feedback",
        "description": (
            "Registrer Mortens reaksjon på ETT forslag fra suggestions_fetch: tatt "
            "(was_accepted=true → acted) eller avvist (was_accepted=false → dismissed). "
            "Dette er det ENESTE konsumpsjonssignalet i forslags-livssyklusen (BL-2652) og "
            "mater læringsløkka som justerer framtidige forslag. Bruk id + type ORDRETT fra "
            "suggestions_fetch-svaret. Ikke kall den uten en faktisk reaksjon fra Morten — "
            "et forslag han bare lot ligge skal IKKE stemples; TTL-en drenerer det selv. "
            "Svarets status=ok betyr MOTTATT av serveren, ikke at noden ble truffet — "
            "si «meldt inn», aldri «registrert på forslaget», med mindre du har lest etter."),
        "parameters": {"type": "object", "properties": {
            "suggestion_id": {"type": "string", "description": "id-feltet fra suggestions_fetch"},
            "suggestion_type": {"type": "string", "description": "type-feltet fra suggestions_fetch"},
            "was_accepted": {"type": "boolean", "description": "true = Morten tar forslaget (acted), false = avvist (dismissed)"},
            "user_id": {"type": "string", "description": "default morten"},
        }, "required": ["suggestion_id", "suggestion_type", "was_accepted"]},
    },
    handler=_suggestion_feedback,
    emoji="✅",
    max_result_size_chars=4000,
)
