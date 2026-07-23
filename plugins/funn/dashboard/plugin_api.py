"""funn plugin-API — GUI-anker for funn-loopen (BL-2368 + Morten-direktivet om
Hermes-forankring). Read-only: faste Cypher via unified-API /graph/query.
Chat-evidens er garantert ikke-klinisk (høsterens A7-eksklusjon skjer FØR noe
når grafens proposal-lag)."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter()
API_BASE = (os.environ.get("SYMBIOSE_API_URL") or "http://192.168.40.12:8010").rstrip("/")

_Q_CHAT_FINDINGS = (
    "MATCH (p:ImprovementProposal {origin:'chat_finding_harvester'}) "
    "OPTIONAL MATCH (p)-[:EVIDENCED_BY]->(c:ConversationTurn) "
    "RETURN p.title AS title, p.category AS category, p.confidence AS confidence, "
    "coalesce(p.status,'proposed') AS status, p.source AS source, "
    "toString(p.created_at) AS created, left(coalesce(c.user_message,''),400) AS user_msg, "
    "left(coalesce(c.assistant_message,''),400) AS assistant_msg "
    "ORDER BY p.created_at DESC"
)
_Q_STATUS = (
    "MATCH (p:ImprovementProposal) "
    "RETURN coalesce(p.status,'proposed') AS status, count(*) AS n ORDER BY n DESC"
)
_Q_LATEST = (
    "MATCH (p:ImprovementProposal) "
    "RETURN coalesce(p.title,p.id) AS title, coalesce(p.origin,p.source,'?') AS origin, "
    "coalesce(p.status,'proposed') AS status, toString(p.created_at) AS created "
    "ORDER BY p.created_at DESC"
)
_Q_WATERMARKS = (
    "MATCH (w:SyncWatermark) WHERE w.id STARTS WITH 'hermes_chat_weld' "
    "RETURN w.id AS id, w.last_msg_id AS last_msg_id, toString(w.updated_at) AS updated"
)
_Q_UNSCANNED = (
    "MATCH (c:ConversationTurn) WHERE c.source IN ['hermes_gui','hermes_worker','native_ai','mcp'] "
    "AND c.finding_scanned_at IS NULL AND c.user_message IS NOT NULL "
    "AND c.assistant_message IS NOT NULL "
    "AND NOT toUpper(coalesce(c.tier,'')) STARTS WITH 'CLINICAL' "
    "AND toLower(coalesce(c.knowledge_domain,'')) <> 'medicine' "
    "RETURN count(c) AS n"
)


def _graph(query: str, limit: int = 100):
    url = f"{API_BASE}/graph/query?query={urllib.parse.quote(query)}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r).get("results", [])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"graf utilgjengelig: {e}")


@router.get("/findings")
def findings():
    return {"findings": _graph(_Q_CHAT_FINDINGS, 100)}


@router.get("/summary")
def summary():
    return {"status": _graph(_Q_STATUS, 30),
            "latest": _graph(_Q_LATEST, 15),
            "watermarks": _graph(_Q_WATERMARKS, 10),
            "unscanned": _graph(_Q_UNSCANNED, 1)}
