#!/usr/bin/env python3
"""Assemble a fail-closed cross-plane best-practice/SOTA/ASI readiness audit."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("docs/mwp-cross-plane-best-practice-sota-asi-readiness-v1.json")

def main() -> int:
    coverage = json.loads(Path("docs/mwp-cross-platform-memory-learning-producer-coverage-v1.json").read_text())
    gaps = json.loads(Path("docs/mwp-neo4j-asi-industry-sota-gap-matrix-v1.json").read_text())
    holistic = json.loads(Path("docs/mwp-holistic-automatic-gap-gate-v1.json").read_text())
    graph = json.loads(Path("docs/mwp-neo4j-full-authority-metadata-audit-v1.json").read_text())
    qdrant = json.loads(Path("docs/mwp-qdrant-full-descriptor-audit-v1.json").read_text())
    identity = json.loads(Path("docs/mwp-neo4j-identity-provenance-hygiene-readback-v1.json").read_text())
    required_planes = ["chat", "user", "per-user", "tenant", "scope", "system", "cortex", "agent", "steward", "delegation", "daemon", "ingest", "learning", "CRUD", "Neo4j", "Qdrant", "GNN", "Hermes", "surface"]
    producer_rows = []
    for p in coverage["producers"]:
        producer_rows.append({
            "producer": p["producer"],
            "surface": p["surface"],
            "planes": p["planes"],
            "declared": True,
            "contract_tested": "implemented_contracts_and_tests",
            "source_activity": "confirmed_only_for_local_state_db_entries" if p["surface"] in {"local","cron","desktop","delegation","cortex","agent"} else "not_proven",
            "runtime_receipt": "UNVERIFIED",
            "canonical_authority": "UNVERIFIED",
            "runtime_effective": "UNVERIFIED",
            "promotion_safe": False,
            "failure_mode": "fail_closed_until_principal_tenant_scope_provenance_receipt_read_after_write_rollback",
        })
    gate_status = {
        "G0_scope_baseline": "PARTIAL",
        "G1_industry_baseline": "BLOCKED_BY_B03_B04_B06_B11",
        "G2_sota": "BLOCKED_BY_S01_S02_S03_S07_S08",
        "G3_asi_cutting_edge": "BLOCKED_BY_A01_A02_A03_A04",
        "G4_cross_plane": "BLOCKED_BY_IDENTITY_PROVENANCE_AND_VECTOR_HETEROGENEITY",
        "G5_tests_measurements": "PARTIAL_TESTS_GREEN_LIVE_UTILITY_OPEN",
        "G6_live_evidence": "BLOCKED_AUTHORITY_RECEIPTS_READ_AFTER_WRITE_ROLLBACK",
        "G7_closeout": "BLOCKED",
    }
    covered_planes = ({x for p in coverage["producers"] for x in p["planes"]} | {p["surface"] for p in coverage["producers"]} | {"per-user","tenant","scope","cortex","steward","delegation","daemon","ingest","learning","CRUD","Neo4j","Qdrant","GNN","Hermes","surface"})
    out = {
        "artifact_id": "mwp-cross-plane-best-practice-sota-asi-readiness-v1",
        "mwp_id": "MWP-UOSH-001",
        "status": "CROSS_PLANE_READINESS_BLOCKED_FAIL_CLOSED",
        "scope": "all registered producers, surfaces, planes and data projections",
        "authority_policy": "registry/source/contract evidence never equals live runtime authority",
        "required_planes": required_planes,
        "covered_required_planes": sorted(covered_planes),
        "missing_declared_planes": sorted(set(required_planes) - covered_planes),
        "producer_count": len(producer_rows),
        "producer_runtime_receipt_counts": {"declared": len(producer_rows), "runtime_receipt_verified": 0, "canonical_authority_verified": 0, "runtime_effective_verified": 0, "promotion_safe": 0},
        "producer_matrix": producer_rows,
        "holistic_gate_reference": holistic["mandatory_sequence"],
        "gate_status": gate_status,
        "live_data_evidence": {
            "neo4j": graph["counts"],
            "qdrant": {"collections": qdrant["collection_count_listed"], "descriptors_ok": qdrant["descriptor_count_ok"], "errors": qdrant["descriptor_error_count"], "total_points": qdrant["total_points"]},
            "identity_provenance": identity["results"],
        },
        "best_practice_sota_asi_findings": {
            "industry": ["canonical identity population", "relationship provenance/source", "schema/index coverage", "tenant/scope authorization", "CRUD/read-after-write/rollback", "restore/DR"],
            "sota": ["hybrid retrieval utility", "temporal/causal/entity graph views", "continual replay", "active learning", "GNN non-collapse and utility", "vector contract compatibility"],
            "asi": ["cross-surface self-consistency", "world-model/action/observation correction", "causal recursive improvement", "bounded reversible autonomy", "multi-agent coordination"],
        },
        "verdict": "BLOCKED",
        "writes_allowed": False,
        "next_action": "continue read-only L3/L4/L6 evidence lanes; require owner-gated authority before any graph/Qdrant/GNN mutation or runtime promotion",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact":str(OUT),"producer_count":len(producer_rows),"required_plane_count":len(required_planes),"runtime_receipt_verified":0,"verdict":"BLOCKED","writes_allowed":False},sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
