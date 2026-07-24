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


def _get(path: str, timeout: int = 15) -> str:
    try:
        with urllib.request.urlopen(API_BASE + path, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"HTTP {e.code} fra {path}", "detail": e.read()[:300].decode("utf-8", "replace")})
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__} mot {API_BASE}{path}: {e}"})


def _post(path: str, payload: dict, timeout: int = 30) -> str:
    req = urllib.request.Request(
        API_BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
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
    handler=lambda args, **kw: _get("/api/v1/bootstrap"),
    emoji="🧠",
    max_result_size_chars=8000,
)

registry.register(
    name="symbiose_ask",
    toolset="symbiose",
    schema={
        "name": "symbiose_ask",
        "description": ("Dypt svar fra hele Symbiose (graf + RAG + minne + sensorer). GRUNDIG men "
                        "TREGT (kognitiv pipeline, kan ta minutter) — bruk graph_query/iot_status for raske oppslag."),
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "Spørsmålet, på norsk eller engelsk"},
        }, "required": ["question"]},
    },
    handler=lambda args, **kw: _post("/query", {"query": args.get("question", ""), "user_id": "morten"}, timeout=170),
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
            {"query": args.get("cypher", ""), "limit": _safe_int(args.get("limit"), 25)})),
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
    handler=lambda args, **kw: _post("/api/v1/meta_introspection", {"operation": "introspect", "user_id": "morten"}, timeout=25),
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
