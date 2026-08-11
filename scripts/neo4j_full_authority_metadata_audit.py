#!/usr/bin/env python3
"""Full read-only Neo4j authority metadata audit; no graph writes."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "http://192.168.40.12:8010/neo4j/q"
OUT = Path("docs/mwp-neo4j-full-authority-metadata-audit-v1.json")

def query(cypher: str):
    url = BASE + "?" + urllib.parse.urlencode({"query": cypher})
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read())

def main() -> int:
    labels = query("CALL db.labels()")
    properties = query("CALL db.propertyKeys()")
    relationships = query("CALL db.relationshipTypes()")
    constraints = query("SHOW CONSTRAINTS")
    indexes = query("SHOW INDEXES")
    stats = query("CALL db.stats.retrieve('GRAPH COUNTS')")
    label_set = {x.get("label") for x in labels if x.get("label")}
    constraint_labels = {l for x in constraints for l in (x.get("labelsOrTypes") or []) if x.get("entityType") == "NODE"}
    indexed_labels = {l for x in indexes for l in (x.get("labelsOrTypes") or []) if x.get("entityType") == "NODE"}
    artifact = {
        "artifact_id": "mwp-neo4j-full-authority-metadata-audit-v1",
        "mwp_id": "MWP-UOSH-001",
        "phase": "P7",
        "status": "FULL_NEO4J_AUTHORITY_METADATA_READBACK",
        "mode": "read-only-cypher",
        "authority_route": BASE,
        "queries": ["CALL db.labels()", "CALL db.propertyKeys()", "CALL db.relationshipTypes()", "SHOW CONSTRAINTS", "SHOW INDEXES", "CALL db.stats.retrieve('GRAPH COUNTS')"],
        "counts": {
            "labels": len(label_set),
            "property_keys": len(properties),
            "relationship_types": len(relationships),
            "constraints": len(constraints),
            "indexes": len(indexes),
            "constraint_labels": len(constraint_labels),
            "indexed_labels": len(indexed_labels),
            "labels_without_constraint_or_index": len(label_set - constraint_labels - indexed_labels),
            "labels_with_constraint_without_index": len(constraint_labels - indexed_labels),
            "labels_with_index_without_constraint": len(indexed_labels - constraint_labels),
            "vector_indexes": sum(1 for x in indexes if x.get("type") == "VECTOR"),
            "relationship_indexes": sum(1 for x in indexes if x.get("entityType") == "RELATIONSHIP"),
        },
        "constraint_type_counts": dict(Counter(x.get("type") for x in constraints)),
        "index_type_counts": dict(Counter(x.get("type") for x in indexes)),
        "index_state_counts": dict(Counter(x.get("state") for x in indexes)),
        "graph_stats_metadata": {"keys": sorted(stats.keys()) if isinstance(stats, dict) else [], "readback": True},
        "projection_divergence": {"graph_schema_reported_constraints": 0, "graph_schema_reported_indexes": 0, "authority_constraints": len(constraints), "authority_indexes": len(indexes)},
        "labels": sorted(label_set),
        "property_keys": sorted(str(x.get("propertyKey") or x.get("property_key") or x.get("name")) for x in properties if isinstance(x, dict) and (x.get("propertyKey") or x.get("property_key") or x.get("name"))),
        "relationship_types": sorted(str(x.get("relationshipType") or x.get("relationship_type") or x.get("name")) for x in relationships if isinstance(x, dict) and (x.get("relationshipType") or x.get("relationship_type") or x.get("name"))),
        "writes_allowed": False,
        "next_action": "classify labels/properties/relationships by owner, namespace, lifecycle and canonical/derived role before repair",
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(OUT), "counts": artifact["counts"], "writes_allowed": False}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
