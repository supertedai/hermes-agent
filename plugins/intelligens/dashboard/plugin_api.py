"""intelligens plugin-API — synliggjør intelligens-baseline-loopen (BL-2409,
ADR-019). Read-only: faste Cypher via unified-API /graph/query. Ingen skriv —
seglingen er Mortens governance (CLI), evalen skrives av cron. Dette er kun
vinduet inn i den ærlige, deskriptive målingen."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter()
API_BASE = (os.environ.get("SYMBIOSE_API_URL") or "http://192.168.40.12:8010").rstrip("/")

_Q_II = (
    "MATCH (p:EvolutionPoint) WHERE p.ii IS NOT NULL "
    "RETURN toString(p.day) AS day, p.ii AS ii, p.ii_problem_solving AS problem_solving, "
    "p.ii_calibration AS calibration, p.ii_n_exams AS n_exams, p.ii_status AS status "
    "ORDER BY p.day DESC"
)
_Q_BASELINES = (
    "MATCH (b:IntelligenceBaseline) "
    "RETURN b.suite_version AS version, b.status AS status, b.n_held_out AS n_held_out, "
    "coalesce(b.baseline_problem_solving, b.proposed_baseline_problem_solving) AS baseline, "
    "b.sealed_by AS sealed_by, toString(b.sealed_at) AS sealed_at, b.domains_json AS domains "
    "ORDER BY b.suite_version"
)
_Q_EVAL = (
    "MATCH (sc:IntelligenceScore) "
    "RETURN toString(sc.at) AS at, sc.current AS current, sc.baseline AS baseline, "
    "sc.delta AS delta, sc.verdict AS verdict, sc.fresh_frac AS fresh_frac "
    "ORDER BY sc.at DESC LIMIT 30"
)
_Q_OPER = (
    "MATCH (o:IntelligenceOperationalization {id:'v1'}) "
    "RETURN o.active_dims AS active_dims, o.pending_dims AS pending_dims, "
    "o.phase AS phase, o.never_optimization_target AS guarded"
)


def _graph(query: str, limit: int = 100):
    url = f"{API_BASE}/graph/query?query={urllib.parse.quote(query)}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r).get("results", [])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"graf utilgjengelig: {e}")


@router.get("/loop")
def loop():
    return {"ii": _graph(_Q_II, 60), "baselines": _graph(_Q_BASELINES, 10),
            "eval": _graph(_Q_EVAL, 30), "operationalization": _graph(_Q_OPER, 1)}
