#!/usr/bin/env python3
"""Read-only bounded Qdrant descriptor audit; no writes or mutations."""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "http://192.168.40.12:6333"
OUT = Path("docs/mwp-qdrant-full-descriptor-audit-v1.json")

def get(path: str, attempts: int = 3):
    last = None
    for n in range(attempts):
        try:
            with urllib.request.urlopen(BASE + path, timeout=15) as r:
                return json.loads(r.read())
        except Exception as exc:
            last = exc
            if n + 1 < attempts:
                time.sleep(0.25 * (n + 1))
    if last is not None:
        raise last
    raise RuntimeError("request failed without an exception")

def main() -> int:
    root = get("/")
    listed = get("/collections").get("result", {}).get("collections", [])
    names = [x["name"] for x in listed]
    descriptors = []
    errors = []
    for index, name in enumerate(names, 1):
        try:
            result = get("/collections/" + urllib.parse.quote(name, safe="")).get("result", {})
            params = result.get("config", {}).get("params", {})
            vectors = params.get("vectors", {})
            if isinstance(vectors, dict) and "size" in vectors:
                vector_signature = [{"size": vectors.get("size"), "distance": vectors.get("distance")}]
            elif isinstance(vectors, dict):
                vector_signature = [
                    {"name": key, "size": value.get("size"), "distance": value.get("distance")}
                    for key, value in sorted(vectors.items()) if isinstance(value, dict)
                ]
            else:
                vector_signature = []
            descriptors.append({
                "name": name,
                "status": result.get("status"),
                "points": result.get("points_count"),
                "vectors": vector_signature,
                "payload_index_count": len(result.get("payload_schema") or {}),
            })
        except Exception as exc:
            errors.append({"name": name, "error": type(exc).__name__, "detail": str(exc)})
        if index % 10 == 0:
            print(f"AUDIT_PROGRESS {index}/{len(names)}", file=sys.stderr, flush=True)
    status_counts = Counter(x.get("status") for x in descriptors)
    signatures = Counter(json.dumps(x.get("vectors"), sort_keys=True) for x in descriptors)
    payload_counts = Counter(x.get("payload_index_count") for x in descriptors)
    artifact = {
        "artifact_id": "mwp-qdrant-full-descriptor-audit-v1",
        "mwp_id": "MWP-UOSH-001",
        "phase": "P7",
        "status": "FULL_QDRANT_DESCRIPTOR_AUDIT_READ_ONLY",
        "mode": "read-only-http",
        "endpoint": BASE,
        "qdrant_version": root,
        "collection_count_listed": len(names),
        "descriptor_count_ok": len(descriptors),
        "descriptor_error_count": len(errors),
        "status_counts": dict(status_counts),
        "vector_signatures": {key: value for key, value in signatures.items()},
        "payload_index_count_distribution": {str(key): value for key, value in payload_counts.items()},
        "total_points": sum((x.get("points") or 0) for x in descriptors),
        "zero_point_collections": sum(1 for x in descriptors if not x.get("points")),
        "descriptors": descriptors,
        "errors": errors,
        "writes_allowed": False,
        "next_action": "compare full Qdrant descriptors with Neo4j canonical identity, scope/provenance and GNN contracts",
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(OUT),
        "collection_count": len(names),
        "descriptor_count_ok": len(descriptors),
        "descriptor_error_count": len(errors),
        "writes_allowed": False,
    }, sort_keys=True))
    return 0 if not errors else 2

if __name__ == "__main__":
    raise SystemExit(main())
