"""symbiose_tools.py — NATIVE Symbiose-verktøy for Opus-GUI-en (fork-gren symbiose-opus).

Morten-direktiv 2026-07-23: «sørg for at Hermes :9119 er Opus nativ, ikke MCP» — Symbiose-
evnene skal være førsteklasses innebygde verktøy, ikke påmontert via MCP-protokollaget.
Gevinst målt mot MCP-ruten: 7 stramme skjemaer i stedet for 25+ (prefill-økonomi på den
~9,5 tok/s lokale cortex-kvanten), direkte HTTP til unified API på flåten (ingen
gateway-hopp, ingen MCP-sesjonslag), og verktøyflaten KURATERT I KODE.

Auto-oppdages av tools/registry.discover_builtin_tools (toppnivå registry.register-kall).
Kun stdlib (urllib) — ingen nye avhengigheter i forken.

SIKKERHETSKONTRAKT (arver BL-2289-reviewens allowlist-beslutning):
  - Kliniske verktøy (A7), mattermost-POST, Tier-4 (fill_gap) og kode-muterende verktøy
    er BEVISST IKKE implementert her — aktivering er Mortens beslutning, ikke en omvei.
  - graph_query går mot /graph/query som er READ-ONLY server-side (unified API).
  - symbiose_write går mot orchestrator-ruten /api/v1/write (gatet server-side).
Alle endepunkter er verifisert live 2026-07-23 mot http://192.168.40.12:8010.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from tools.registry import registry

API_BASE = os.environ.get("SYMBIOSE_API_URL", "http://192.168.40.12:8010").rstrip("/")

# IoT-domener → verifiserte unified-API-ruter (alle GET, live-data).
_IOT_ROUTES = {
    "energy": "/victron/realtime",
    "weather": "/weather/realtime",
    "power_price": "/tibber/realtime",
    "security": "/pa440/status",
}


def _safe_int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _get(path: str, timeout: int = 15, user_id: str = "") -> str:
    # BL-2790: X-User-ID = innsenderens identitet; server-siden owner-scoper
    # recall på den (BL-2783/2786/2789). Tom = legacy → eier-default server-side.
    req = urllib.request.Request(
        API_BASE + path,
        headers=({"X-User-ID": user_id} if user_id else {}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"HTTP {e.code} fra {path}", "detail": e.read()[:300].decode("utf-8", "replace")})
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__} mot {API_BASE}{path}: {e}"})


def _caller_uid(kw: dict) -> str:
    """BL-2790: identiteten til turn-innsenderen (sid→bruker-registeret på .15).

    Tom streng = legacy/admin-æra → serverne bruker eier-default (morten).
    Korrupt identitets-infra PROPAGERER (registry.dispatch fanger og returnerer
    error-JSON) — recall skal feile høyt, aldri falle tilbake til eier-data.
    """
    from hermes_cli.dashboard_auth.session_identity import get_identity
    return get_identity(str(kw.get("session_id") or "")) or ""


def _post(path: str, payload: dict, timeout: int = 30, user_id: str = "") -> str:
    _hdrs = {"Content-Type": "application/json"}
    if user_id:
        _hdrs["X-User-ID"] = user_id  # BL-2790, se _get
    req = urllib.request.Request(
        API_BASE + path, data=json.dumps(payload).encode(),
        headers=_hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"HTTP {e.code} fra {path}", "detail": e.read()[:300].decode("utf-8", "replace")})
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__} mot {API_BASE}{path}: {e}"})


registry.register(
    name="opus_brief",
    toolset="symbiose",
    schema={
        "name": "opus_brief",
        "description": "Sesjonsbrief fra Symbiose: systemtilstand, grafen, mål og fokus. Kall ved sesjonstart.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/api/v1/bootstrap?refresh=true", timeout=20),
    emoji="🧠",
    max_result_size_chars=8000,
)

registry.register(
    name="symbiose_ask",
    toolset="symbiose",
    schema={
        "name": "symbiose_ask",
        "description": ("Dyp fakta-retrieval fra Symbiose (RAG + graf-noder) for et spørsmål. "
                        "Returnerer RÅ fakta/kilder — DU syntetiserer svaret selv (ingen server-side "
                        "LLM-syntese: raskere+billigere, chatten er bedre på syntese). graph_query for presis Cypher."),
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "Spørsmålet, på norsk eller engelsk"},
        }, "required": ["question"]},
    },
    # BL (2026-07-26, Morten «ta bort syntesen — chatten er bedre + fordyrende ledd»): symbiose_ask
    # traff før syntetiserende /query (2-3 LLM-kall server-side, 170s timeout/hang). Nå fakta-only
    # /rag/search (rask ~0.1s, RAG+graf-noder); chatten (120B+MoA) syntetiserer. Ingen dobbel-LLM.
    handler=lambda args, **kw: _post("/rag/search", {"query": args.get("question", ""), "limit": 12}, timeout=25, user_id=_caller_uid(kw)),
    emoji="🔮",
    max_result_size_chars=12000,
)

registry.register(
    name="graph_query",
    toolset="symbiose",
    schema={
        "name": "graph_query",
        "description": "Kjør READ-ONLY Cypher mot Symbiose-grafen (8M+ noder). Raskt. Server-side lesebeskyttet.",
        "parameters": {"type": "object", "properties": {
            "cypher": {"type": "string", "description": "Cypher-spørring, f.eks. MATCH (g:OpusGoal) RETURN g.title LIMIT 5"},
            "limit": {"type": "integer", "description": "Radgrense (default 25)"},
        }, "required": ["cypher"]},
    },
    handler=lambda args, **kw: _get(
        "/graph/query?" + urllib.parse.urlencode(
            # defensiv koersjon (reviewer BL-2298): modell-emittert limit kan være "all" e.l.
            # — feilveier skal returnere JSON, aldri kaste ValueError ut av handleren.
            {"query": args.get("cypher", ""), "limit": _safe_int(args.get("limit"), 25)}),
        user_id=_caller_uid(kw)),
    emoji="🕸️",
    max_result_size_chars=10000,
)

registry.register(
    name="symbiose_write",
    toolset="symbiose",
    schema={
        "name": "symbiose_write",
        "description": ("Lagre et varig faktum/minne/innsikt i Symbiose (gatet server-side via "
                        "orchestratoren). Bruk når Morten sier «lagre/husk dette»."),
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "description": "Type, f.eks. fact, memory, insight, decision"},
            "content": {"type": "string", "description": "Innholdet som skal lagres"},
        }, "required": ["kind", "content"]},
    },
    handler=lambda args, **kw: _post("/api/v1/write", {
        "type": args.get("kind", "memory"), "operation": "create",
        "data": {"content": args.get("content", ""), "source": "opus-gui-native"}}),
    emoji="✍️",
)

registry.register(
    name="iot_status",
    toolset="symbiose",
    schema={
        "name": "iot_status",
        "description": "Live hjemme-IoT: energy (Victron/batteri/sol), weather (Ecowitt), power_price (Tibber), security (PA-440).",
        "parameters": {"type": "object", "properties": {
            "domain": {"type": "string", "enum": list(_IOT_ROUTES), "description": "Hvilket domene"},
        }, "required": ["domain"]},
    },
    handler=lambda args, **kw: (
        _get(_IOT_ROUTES[args["domain"]]) if args.get("domain") in _IOT_ROUTES
        else json.dumps({"error": f"ukjent domene — velg blant {sorted(_IOT_ROUTES)}"})),
    emoji="🏠",
    max_result_size_chars=6000,
)

registry.register(
    name="research_status",
    toolset="symbiose",
    schema={
        "name": "research_status",
        "description": "EFC-forskningsstatus: helse-score, signaler, validering (passert/totalt), inferens.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/api/v1/research", timeout=20),
    emoji="🔬",
    max_result_size_chars=8000,
)

registry.register(
    name="system_health",
    toolset="symbiose",
    schema={
        "name": "system_health",
        "description": "Symbiose-flåtens helse: containere, oppetid, ressurser (meta-introspeksjon).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _post("/api/v1/meta_introspection", {"operation": "introspect", "user_id": _caller_uid(kw) or "morten"}, timeout=25),
    emoji="💓",
    max_result_size_chars=8000,
)


registry.register(
    name="fleet_status",
    toolset="symbiose",
    schema={
        "name": "fleet_status",
        "description": ("Worker/daemon-flatens tilstand: total, helse-fordeling, problem-daemons "
                        "(ikke-healthy) og stale (healthy men gammel heartbeat). Bruk for a svare pa "
                        "hvilke workers finnes og hvordan star de."),
        "parameters": {"type": "object", "properties": {
            "stale_minutes": {"type": "integer", "description": "Heartbeat eldre enn dette (min) = stale (default 30)"},
        }, "required": []},
    },
    handler=lambda args, **kw: _get("/fleet/status?stale_minutes=%d&problem_limit=40" % _safe_int(args.get("stale_minutes"), 30)),
    emoji="\U0001F681",
    max_result_size_chars=10000,
)

registry.register(
    name="learning_status",
    toolset="symbiose",
    schema={
        "name": "learning_status",
        "description": "Symbioses laerings-loop: erfaringer, laerte monstre, suksessrate, reparasjoner (self-improvement).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/learning/status", timeout=20),
    emoji="\U0001F4C8",
    max_result_size_chars=8000,
)


registry.register(
    name="active_goals",
    toolset="symbiose",
    schema={
        "name": "active_goals",
        "description": "Aktive OpusGoals med prioritet (P0-P3) og status. Bruk for malbilde / hva bor gjores.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/graph/query?" + urllib.parse.urlencode({
        "query": "MATCH (g:OpusGoal) WHERE g.status=\x27active\x27 RETURN g.title AS title, g.priority AS prio, g.status AS status ORDER BY g.priority LIMIT 20",
        "limit": 20})),
    emoji="\U0001F3AF",
    max_result_size_chars=6000,
)

registry.register(
    name="recent_changes",
    toolset="symbiose",
    schema={
        "name": "recent_changes",
        "description": "Nylige beslutninger/innsikter skrevet til Symbiose-grafen (hva ble nylig endret eller laert).",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Antall (default 10)"},
        }, "required": []},
    },
    handler=lambda args, **kw: _get("/graph/query?" + urllib.parse.urlencode({
        "query": "MATCH (f:SelfKnowledgeFact) WHERE f.kind IN [\x27decision\x27,\x27insight\x27,\x27plan\x27] RETURN f.key AS key, f.kind AS kind, toString(f.updated_at) AS at ORDER BY f.updated_at DESC LIMIT " + str(_safe_int(args.get("limit"), 10)),
        "limit": _safe_int(args.get("limit"), 10)})),
    emoji="\U0001F4DD",
    max_result_size_chars=6000,
)


registry.register(
    name="gnn_similar",
    toolset="symbiose",
    schema={
        "name": "gnn_similar",
        "description": ("Finn konsepter GNN-naermest et gitt konsept (multi-tier embedding-similaritet). "
                        "DIREKTE GNN-lag, ikke via den trege ask-pipelinen. Konseptnavn ma matche eksakt "
                        "(bruk graph_query for a finne gyldige navn forst)."),
        "parameters": {"type": "object", "properties": {
            "concept": {"type": "string", "description": "Eksakt konseptnavn"},
            "top_k": {"type": "integer", "description": "Antall (default 8)"},
        }, "required": ["concept"]},
    },
    handler=lambda args, **kw: _get("/gnn/similar/" + urllib.parse.quote(str(args.get("concept",""))) + "?top_k=" + str(_safe_int(args.get("top_k"), 8)), timeout=40),
    emoji="\U0001F578",
    max_result_size_chars=6000,
)


registry.register(
    name="qdrant_search",
    toolset="symbiose",
    schema={
        "name": "qdrant_search",
        "description": ("DIREKTE semantisk/vektor-sok i Symbiose Qdrant (RAG-laget) — ikke via den trege "
                        "ask-pipelinen. Rask etter oppvarming (forste cold-kall ~40-60s). Collections: "
                        "efc, private, theory, semantic_mesh m.fl."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Soketekst"},
            "collection": {"type": "string", "description": "Qdrant-collection (default efc)"},
            "limit": {"type": "integer", "description": "Antall treff (default 5)"},
        }, "required": ["query"]},
    },
    handler=lambda args, **kw: _post("/api/v1/qdrant/search", {
        "query": args.get("query",""), "collection": args.get("collection") or "efc",
        "limit": _safe_int(args.get("limit"), 5)}, timeout=100, user_id=_caller_uid(kw)),
    emoji="\U0001F50D",
    max_result_size_chars=9000,
)


registry.register(
    name="propose_action",
    toolset="symbiose",
    schema={
        "name": "propose_action",
        "description": ("Foresla en system-/fleet-handling (f.eks. restart av en daemon, en fiks). Skriver et "
                        "GATET forslag som IKKE kjores for Morten godkjenner (propose-first, aldri direkte "
                        "aktuering). Returnerer proposal_id + risk_level. Bruk nar du vil ENDRE noe, ikke bare observere."),
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Konkret kommando/handling som foreslas"},
            "reasoning": {"type": "string", "description": "Begrunnelsen for handlingen"},
        }, "required": ["command", "reasoning"]},
    },
    handler=lambda args, **kw: _post("/agi/proposals/command", {
        "command": args.get("command",""), "reasoning": args.get("reasoning",""),
        "created_by": "opus-hermes-gui"}),
    emoji="\U0001F4E4",
    max_result_size_chars=3000,
)

registry.register(
    name="list_proposals",
    toolset="symbiose",
    schema={
        "name": "list_proposals",
        "description": "List gatede forslag (propose->approve->execute) med status og risk. Se hva som venter pa Mortens godkjenning.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/agi/proposals/?limit=15", timeout=20),
    emoji="\U0001F4CB",
    max_result_size_chars=8000,
)


registry.register(
    name="learning_trends",
    toolset="symbiose",
    schema={
        "name": "learning_trends",
        "description": ("Laerings-EFFEKTIVITET over tid: parameter-trender, korreksjonsrate, hva som "
                        "forbedres eller degraderer. For a se om systemet faktisk laerer bedre."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/api/v1/learning/trends/" + urllib.parse.quote(_caller_uid(kw) or "morten"), timeout=20),
    emoji="\U0001F4C8",
    max_result_size_chars=7000,
)

registry.register(
    name="shadow_tests",
    toolset="symbiose",
    schema={
        "name": "shadow_tests",
        "description": ("Shadow/A-B-tester: for-etter-maling av endringer (prompts, parametre, invariants) "
                        "mot baseline FOR de gar live. Kjernen i kontrollert laering og rollback."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: _get("/api/v1/learning/shadow-tests", timeout=20),
    emoji="\U0001F9EA",
    max_result_size_chars=7000,
)


def _science_compute(args: dict) -> str:
    """BL-2560: bro til systemets vitenskapelige motorer — aktuator-gatet SERVER-SIDE (.12:8010),
    aldri lokalt: .15 har bevisst ingen graf-creds, saa gate-oppslag og motorer kjoerer der creds bor."""
    agent = "hermes-pilot-001"  # GUI-pilotens :FleetAgent-id — grants/nektelser scopes hit
    tool = (args.get("tool") or "").strip()
    if not tool:
        return _get("/api/v1/compute/available?agent=" + urllib.parse.quote(agent), timeout=30)
    payload: dict = {"agent": agent, "tool": tool, "domain": (args.get("domain") or "").strip()}
    if args.get("target"):
        payload["target"] = args["target"]
    iv = args.get("intervention")
    if iv:
        if isinstance(iv, str):
            try:
                iv = json.loads(iv)
            except ValueError:
                pass  # streng-form er gyldig — serveren koerserer
        payload["intervention"] = iv
    # BL-2576 forecast-parametre (live tidsserie-prognose).
    if args.get("metric"):
        payload["metric"] = args["metric"]
    if args.get("horizon_hours"):
        payload["horizon_hours"] = _safe_int(args.get("horizon_hours"), 24)
    if args.get("source"):
        payload["source"] = args["source"]
    return _post("/api/v1/compute/run", payload, timeout=90)


registry.register(
    name="science_compute",
    toolset="symbiose",
    schema={
        "name": "science_compute",
        "description": (
            "Kjoer Symbioses EGNE vitenskapelige motorer, aktuator-gatet fail-closed, ALLTID domene-"
            "isolert (aldri EFC/kosmos i et oekonomi-spm). tool=domains (VIS hvilke domener som har "
            "kausal struktur — kall FOER de andre) | probability (ANBEFALT for «hvor sannsynlig er X»: "
            "orkestrerer strukturell identifiserbarhet + konjugat Bayesiansk posterior → P(sann) med "
            "94% kredibilitetsintervall + evidensklasse; krever target=utfall, valgfri intervention="
            "aarsak, domain) | sources (HELE datatrakten: alle akser + hva som er spoerrbart) | "
            "evidence (surface akkumulert evidens for ET domene som mangler kausal SCM: cyber=CVE, "
            "regulation=RegulatoryAction, cognition=Mechanism/Hypothesis — krever domain) | forecast "
            "(LIVE TEMPORAL prognose «gaar X opp/ned neste N timer»: "
            "P(opp/ned) + prediktivt intervall fra :IoTReading-tidsserie; krever metric=f.eks. "
            "price_total_hjem/battery_soc, valgfri horizon_hours) | do_calculus (kun strukturell "
            "identifiserbarhet) | bayes (ren evidens-posterior) | scm (SKRIVER hypotese-kanter) | "
            "nuts | mcmc (.11 — kan svare «ikke wiret»). Uten tool: vis tilgang. Disiplin: "
            "INSUFFICIENT = tomt/manglende data, IKKE bevis for det motsatte; oppgi ALLTID intervallet "
            "med punktestimatet; SKILL evidens-posterior (kausal, grafen) fra forecast (temporal, live "
            "data); forecast reliability=LAV betyr «kan ikke skille retning», ikke «stabilt»; "
            "resultater er evidens, ikke konklusjoner — vitenskapelig tilskrivning er Mortens."
        ),
        "parameters": {"type": "object", "properties": {
            "tool": {"type": "string",
                     "description": "domains | probability | do_calculus | bayes | scm | nuts | mcmc "
                                    "(utelat for tilgangsliste)"},
            "target": {"type": "string", "description": "Utfallsvariabel (probability/bayes/do_calculus)"},
            "intervention": {"type": "string",
                             "description": "Intervensjon som JSON, f.eks. {\"X\": \"hoy\"}"},
            "domain": {"type": "string", "description": "SCM-domene i grafen — PÅKREVD for probability/"
                                                        "bayes (kall tool=sources/domains for liste); "
                                                        "ingen default"},
            "metric": {"type": "string", "description": "forecast: ticker (EQNR.OL) ELLER IoT-metrikk "
                                                        "(price_total_hjem, battery_soc)"},
            "horizon_hours": {"type": "integer", "description": "forecast: horisont i timer (IoT, default 24)"},
        }, "required": []},
    },
    handler=lambda args, **kw: _science_compute(args or {}),
    emoji="\U0001F52C",
    max_result_size_chars=10000,
)


# WP7 (BL-2814): consent-bevisst personlig-fakta-verktoy. Kaller det consent-gatede
# .12-endepunktet (apply_consent=true) -> domener brukeren har merket «privat»
# utelates automatisk fra recall. Per bruker via _caller_uid (BL-2790-identitet).
_MINE_FAKTA_DOMAINS = frozenset(('IDENTITY', 'FAMILY', 'WORK', 'PROJECTS', 'SKILLS', 'HEALTH', 'OWNERSHIP', 'LOCATION', 'FINANCE', 'ENVIRONMENT', 'AGENTS', 'THEORIES', 'IOT'))


def _mine_fakta(args, **kw):
    # WP7 (BL-2814): FAIL-CLOSED - personlige fakta krever en identifisert sesjon.
    # Uten identitet returneres feil (ikke eier-default), sa en uregistrert
    # ikke-eier-sesjon aldri kan fa eierens fakta. BL-3964/BL-3965 sorger for at
    # eier-sesjoner FAKTISK er registrert under den durable id-en verktoylaget
    # slar opp med - for dem svarte denne grenen alltid, ogsa for eieren selv.
    uid = _caller_uid(kw)
    if not uid:
        return json.dumps({"error": "no_identity",
                           "detail": "Personlige Life Contract-fakta krever en identifisert sesjon."})
    # BL-3965: 160 fakta over 10 domener sprengte max_result_size_chars, sa
    # svaret ble kuttet midt i og resten var usynlig for modellen - den sa
    # PROJECTS og meldte det som "minst disse". `.12`-endepunktet stotter
    # `domain`, sa be om ett domene av gangen nar fullstendighet trengs.
    # Utelatt domain = samme fulle oppslag som for, na med hoyere takhoyde.
    q = {"user_id": uid, "apply_consent": "true"}
    dom = (args or {}).get("domain")
    if isinstance(dom, str) and dom.strip():
        dom = dom.strip().upper()
        # BL-3965 reviewer-funn: uten enum tar skjemaet enhver streng.
        # Malt: domain="PROJECT" (entall-skrivefeil for "PROJECTS") gir 100
        # tomme UNKNOWN-poster (predicate=None, value=None) meldt som 100
        # fakta - en konfabulasjonsvektor, ikke bare et tomt svar. Avvis her,
        # for kallet nar .12, i stedet for a la et gjettet domenenavn stille
        # produsere skygge-data.
        if dom not in _MINE_FAKTA_DOMAINS:
            return json.dumps({
                "error": "unknown_domain",
                "detail": f"Ukjent domene {dom!r}. Gyldige: "
                          + ", ".join(sorted(_MINE_FAKTA_DOMAINS)),
            }, ensure_ascii=False)
        q["domain"] = dom
    return _get("/life-contract/facts?" + urllib.parse.urlencode(q), user_id=uid)


registry.register(
    name="mine_fakta",
    toolset="symbiose",
    schema={
        "name": "mine_fakta",
        "description": (
            "Brukerens egne Life Contract-fakta (identitet, arbeid, helse, familie, "
            "prosjekter osv.), gruppert per domene. Respekterer personvern: domener "
            "brukeren selv har merket «privat» utelates automatisk. Bruk nar brukeren "
            "spor om hva du vet om dem, eller trenger deres egne kanoniske fakta."),
        "parameters": {"type": "object", "properties": {
            "domain": {"type": "string",
                       "enum": sorted(_MINE_FAKTA_DOMAINS),
                       "description": "Valgfritt: hent KUN ett domene. Utelat for alle - "
                                      "men et fullt oppslag kan naerme seg takhoyden, sa be "
                                      "per domene nar du trenger fullstendighet."},
        }, "required": []},
    },
    handler=_mine_fakta,
    emoji="\U0001F4CB",
    max_result_size_chars=60000,
)


registry.register(
    name="recall_enrich",
    toolset="symbiose",
    schema={
        "name": "recall_enrich",
        "description": (
            "GLOBAL recall->inferens (BL-2862): kjor KAUSAL (bayes-posterior) + TEMPORAL (forecast) for "
            "hver oppgitt entitet, pa tvers av ALLE domener inkl EFC/cosmos (kandidat-flagg, ingen DOI), "
            "A7-gatet. Bruk nar et svar bor baere kausal/temporal resonnering, ikke bare semantisk recall "
            "- f.eks. mal/variabler nevnt i sporsmalet (priser, drivere, makro, EFC-storrelser). "
            "Returnerer per entitet: causal (p_true + n_edges + evidensklasse per domene) og temporal "
            "(retning + driver + neste-periode-intervall)."),
        "parameters": {"type": "object", "properties": {
            "entities": {"type": "array", "items": {"type": "string"},
                         "description": "entiteter a inferere, f.eks. [\"NO2 spot price\", \"Energy Flow\"]"},
        }, "required": ["entities"]},
    },
    handler=lambda args, **kw: _post(
        "/api/v1/compute/recall_enrich",
        {"entities": args.get("entities", [])}, user_id=_caller_uid(kw)),
    emoji="\U0001F9E0",
    max_result_size_chars=8000,
)


# WP6.2 (BL-2921): bind en livsdomene-query til dens ansvarlige domene-steward +
# kontrakt i chat-oyeblikket. Read-only mot .12 /life-contract/steward-context.
def _steward_context(args, **kw):
    domain = (args.get("domain") or "").strip()
    if not domain:
        return json.dumps({"error": "domain_required",
                           "detail": "Oppgi livsdomene: HEALTH|FINANCE|IDENTITY|WORK|PROJECTS|FAMILY|OWNERSHIP|ENVIRONMENT|LOCATION"})
    uid = _caller_uid(kw)
    params = {"domain": domain}
    if uid:
        params["user_id"] = uid
    action = (args.get("action") or "").strip()
    if action:
        params["action"] = action
    return _get("/life-contract/steward-context?" + urllib.parse.urlencode(params), user_id=uid)


registry.register(
    name="steward_context",
    toolset="symbiose",
    schema={
        "name": "steward_context",
        "description": (
            "Bind et livsdomene-spm til dets ansvarlige domene-steward + kontrakt FOER du "
            "handler pa domenedata. Returnerer steward (Asklepios/HELSE, Plutus/OKONOMI, "
            "Janus/IDENTITET, Hephaistos/ARBEID, Daedalus/PROSJEKTER, Hestia/FAMILIE, "
            "Gaia/EIENDOM, Helios/MILJO, Terminus/STED), hva den kan overflate, og output-regel "
            "(HELSE=never_auto_shared: ALDRI raa helsedata). VIKTIG handlingsklasse: "
            "morten_hand = FORBUDT for deg (betaling/overforing/handel/signering/BankID) - Morten "
            "gjor det selv, et 'ja' autoriserer deg IKKE; approval_required = utfor kun etter "
            "Mortens ja; allowed = fritt. Bruk action= for a klassifisere en konkret handling."),
        "parameters": {"type": "object", "properties": {
            "domain": {"type": "string",
                       "description": "HEALTH|FINANCE|IDENTITY|WORK|PROJECTS|FAMILY|OWNERSHIP|ENVIRONMENT|LOCATION"},
            "action": {"type": "string",
                       "description": "valgfri handling a klassifisere (transfer_money, send_email, book_appointment ...)"},
        }, "required": ["domain"]},
    },
    handler=_steward_context,
    emoji="\U0001F9ED",
    max_result_size_chars=8000,
)
