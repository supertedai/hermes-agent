"""fleetcron plugin-API — leser flåte-cron-registeret (:FleetCronJob) via
unified-API-ets read-only /graph/query (BL-2363). Hermes' egne cron-jobber
flettes KLIENT-SIDE (samme origin, /api/cron/jobs) — denne API-en rører dem
ikke. Ingen skriveruter: flåte-entries eies av kollektoren (discovery),
Hermes-jobber av native API."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter()
API_BASE = (os.environ.get("SYMBIOSE_API_URL") or "http://192.168.40.12:8010").rstrip("/")

_Q_FLEET = (
    "MATCH (c:FleetCronJob) WHERE coalesce(c._archived,false) = false "
    "RETURN c.host AS host, c.scheduler AS scheduler, c.schedule AS schedule, "
    "c.command AS command, c.label AS label, toString(c.last_seen) AS last_seen "
    "ORDER BY c.host, c.scheduler, c.label"
)


def _graph(query: str, limit: int = 300):
    url = f"{API_BASE}/graph/query?query={urllib.parse.quote(query)}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r).get("results", [])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"graf utilgjengelig: {e}")


@router.get("/fleet")
def fleet():
    return {"jobs": _graph(_Q_FLEET)}
