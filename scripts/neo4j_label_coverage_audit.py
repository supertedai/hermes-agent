#!/usr/bin/env python3
"""Full read-only per-label constraint/index coverage audit."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "http://192.168.40.12:8010/neo4j/q"
OUT = Path("docs/mwp-neo4j-label-coverage-audit-v1.json")

def query(cypher: str):
    url = BASE + "?" + urllib.parse.urlencode({"query": cypher})
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read())

def main() -> int:
    labels = {x["label"] for x in query("CALL db.labels()") if x.get("label")}
    constraints = query("SHOW CONSTRAINTS")
    indexes = query("SHOW INDEXES")
    by_label = {
        label: {"constraints": [], "indexes": [], "classification": "neither"}
        for label in labels
    }
    for row in constraints:
        if row.get("entityType") != "NODE":
            continue
        for label in row.get("labelsOrTypes") or []:
            if label in by_label:
                by_label[label]["constraints"].append({
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "properties": row.get("properties") or [],
                    "propertyType": row.get("propertyType"),
                })
    for row in indexes:
        if row.get("entityType") != "NODE":
            continue
        for label in row.get("labelsOrTypes") or []:
            if label in by_label:
                by_label[label]["indexes"].append({
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "state": row.get("state"),
                    "properties": row.get("properties") or [],
                })
    for label, record in by_label.items():
        has_c = bool(record["constraints"])
        has_i = bool(record["indexes"])
        record["classification"] = "both" if has_c and has_i else "constraint_only" if has_c else "index_only" if has_i else "neither"
    counts = Counter(x["classification"] for x in by_label.values())
    out = {
        "artifact_id": "mwp-neo4j-label-coverage-audit-v1",
        "mwp_id": "MWP-UOSH-001",
        "phase": "P7",
        "status": "FULL_LABEL_COVERAGE_READBACK_OWNER_REVIEW_OPEN",
        "mode": "read-only-cypher",
        "authority_route": BASE,
        "label_count": len(by_label),
        "classification_counts": dict(counts),
        "labels": by_label,
        "safety": {"writes_allowed": False, "promotion": False, "schema_repair": False, "deduplication": False},
        "next_action": "join per-label coverage with owner/domain/lifecycle/property/relationship evidence before repair",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(OUT), "label_count": len(by_label), "classification_counts": dict(counts), "writes_allowed": False}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
