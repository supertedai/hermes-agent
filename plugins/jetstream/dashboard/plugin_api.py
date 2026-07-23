"""Jetstream dashboard plugin — backend API (BL-2348).

Mounted at /api/plugins/jetstream/ by the dashboard plugin system, behind the
session-token auth middleware (same contract as kanban — see its docstring).

Tynt lag over unified-API-ets READ-ONLY /graph/query på flåten (.12:8010) —
samme sikkerhetsmodell som tools/symbiose_tools.py (BL-2289-allowlisten):
ingen graf-credentials på .15, ingen klient-levert Cypher (alle spørringer er
FASTE strenger her; klienten kan bare velge hvilken). Registeret
(:IngestSourceSpec, seedet av AGI-repoets tools/jetstream_registry.py) er
sannhetskilden; denne fila legger ikke egen tilstand.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter()

API_BASE = os.environ.get("SYMBIOSE_API_URL", "http://192.168.40.12:8010").rstrip("/")

# FASTE spørringer — klient-input når aldri Cypher-strengen.
_Q_SOURCES = (
    "MATCH (j:IngestSourceSpec) "
    "OPTIONAL MATCH (j)-[:CONSUMED_BY]->(c) "
    "RETURN j.name AS name, j.source_kind AS kind, j.domain AS domain, "
    "       j.migration_status AS migration, j.consumer_status AS consumer_status, "
    "       j.endpoint_hint AS endpoint, j.legacy_container AS container, "
    "       count(c) AS consumers, toString(j.updated_at) AS updated "
    "ORDER BY j.domain, j.name"
)
_Q_SUMMARY = (
    "MATCH (j:IngestSourceSpec) "
    "RETURN j.migration_status AS migration, j.source_kind AS kind, count(*) AS n"
)


def _graph(query: str, limit: int = 200) -> list[dict]:
    url = API_BASE + "/graph/query?" + urllib.parse.urlencode(
        {"query": query, "limit": limit})
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            payload = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        # bred 502-dekning (reviewer-nit): read-timeout og ikke-JSON-kropp er
        # også "upstream utilgjengelig", ikke 500
        raise HTTPException(status_code=502, detail=f"unified API unreachable: {e}")
    return payload.get("results") or []


@router.get("/sources")
def sources():
    return {"sources": _graph(_Q_SOURCES)}


@router.get("/summary")
def summary():
    rows = _graph(_Q_SUMMARY)
    by_migration: dict = {}
    by_kind: dict = {}
    total = 0
    for r in rows:
        n = int(r.get("n") or 0)
        total += n
        by_migration[r.get("migration") or "?"] = by_migration.get(r.get("migration") or "?", 0) + n
        by_kind[r.get("kind") or "?"] = by_kind.get(r.get("kind") or "?", 0) + n
    return {"total": total, "by_migration": by_migration, "by_kind": by_kind}
