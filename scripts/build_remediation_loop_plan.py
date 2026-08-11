#!/usr/bin/env python3
"""Build a fail-closed remediation loop from live graph/vector readbacks."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("docs/mwp-remediation-loop-plan-v1.json")

def main() -> int:
    graph = json.loads(Path("docs/mwp-neo4j-full-authority-metadata-audit-v1.json").read_text())
    coverage = json.loads(Path("docs/mwp-neo4j-label-coverage-audit-v1.json").read_text())
    qdrant = json.loads(Path("docs/mwp-qdrant-full-descriptor-audit-v1.json").read_text())
    loop = {
        "artifact_id": "mwp-remediation-loop-plan-v1",
        "mwp_id": "MWP-UOSH-001",
        "status": "REMEDIATION_LOOP_ACTIVE_FAIL_CLOSED",
        "mode": "plan_and_verify_no_production_writes",
        "lanes": [
            {
                "id":"L1_PROJECTION_PARITY",
                "target":"graph/schema projection versus /neo4j/q authority",
                "finding":"projection reports zero constraints/indexes while authority reports 181/427",
                "action":"repair projection/read API to consume or reconcile authoritative schema metadata",
                "status":"OWNER_RUNTIME_WRITE_GATE_OPEN",
                "rollback":"revert projection adapter only",
                "evidence":"authority/projection parity readback"
            },
            {
                "id":"L2_LABEL_ONTOLOGY",
                "target":"1065 labels, 10738 properties, 4106 relationships",
                "finding":"749 candidate labels remain unclassified; 852 neither constraint nor index",
                "action":"assign owner/domain/lifecycle/canonical-derived-legacy-quarantine class; then propose scoped constraints/indexes",
                "status":"READONLY_CLASSIFICATION_DONE_OWNER_REVIEW_OPEN",
                "rollback":"no graph mutation until classification receipt"
            },
            {
                "id":"L3_DUPLICATE_DANGLING",
                "target":"canonical identities and relationship endpoints",
                "finding":"not yet fully audited",
                "action":"run duplicate canonical-key and dangling-edge read-only queries; quarantine candidates, never auto-merge",
                "status":"OPEN_READONLY",
                "rollback":"no mutation"
            },
            {
                "id":"L4_QDRANT_CONTRACT",
                "target":"110 collections / 4,965,726 points",
                "finding":"108×4096, 1×512, 1×8; payload-index distribution 107×0,1×2,1×4,1×5",
                "action":"map collection→model/version/dimension/metric/owner/scope/graph identity; quarantine incompatible projections",
                "status":"FULL_DESCRIPTOR_READBACK_DONE_REPAIR_GATE_OPEN",
                "rollback":"isolated rebuild/delete only with owner approval"
            },
            {
                "id":"L5_GNN_HEALTH",
                "target":"active v2.0.0 multi-tier GNN",
                "finding":"collapsed=true, would_abstain=true, cosine=0.8670 > 0.85",
                "action":"shadow diagnose/retrain/evaluate non-collapse, leakage, utility and rollback; block ranking promotion until pass",
                "status":"PROMOTION_BLOCKED_REPAIR_EXPERIMENT_OPEN",
                "rollback":"checkpoint rollback"
            },
            {
                "id":"L6_PROPAGATION",
                "target":"CRUD → Neo4j/Qdrant/GNN/Hermes/surfaces",
                "finding":"contracts/preflight exist; live receipts/read-after-write/rollback incomplete",
                "action":"produce bounded metadata receipts and verify ordering/idempotency/tombstone/read-after-write",
                "status":"OPEN_RUNTIME_AUTHORITY",
                "rollback":"receipt-linked rollback"
            }
        ],
        "observed_inputs": {
            "graph_labels": graph["counts"]["labels"],
            "graph_property_keys": graph["counts"]["property_keys"],
            "graph_relationship_types": graph["counts"]["relationship_types"],
            "graph_constraints": graph["counts"]["constraints"],
            "graph_indexes": graph["counts"]["indexes"],
            "label_coverage": coverage["classification_counts"],
            "qdrant_collections": qdrant["collection_count_listed"],
            "qdrant_descriptors": qdrant["descriptor_count_ok"],
            "qdrant_errors": qdrant["descriptor_error_count"]
        },
        "global_policy": {
            "writes_allowed": False,
            "no_auto_merge": True,
            "no_auto_delete": True,
            "no_gnn_promotion": True,
            "no_qdrant_rebuild": True,
            "continue_independent_readonly_lanes": True
        },
        "next_action": "execute L3 read-only duplicate/dangling audit and L4 collection-to-identity mapping; keep L1/L5/L6 owner/runtime gates parked"
    }
    OUT.write_text(json.dumps(loop, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact":str(OUT),"lanes":len(loop['lanes']),"writes_allowed":False},sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
