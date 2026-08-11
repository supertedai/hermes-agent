#!/usr/bin/env python3
"""Fail-closed census of producer runtime receipt evidence."""
from __future__ import annotations

import json
from pathlib import Path

COVERAGE = Path("docs/mwp-cross-platform-memory-learning-producer-coverage-v1.json")
OUT = Path("docs/mwp-producer-runtime-receipt-census-v1.json")

def main() -> int:
    source = json.loads(COVERAGE.read_text())
    rows = []
    for p in source["producers"]:
        rows.append({
            "producer": p["producer"],
            "surface": p["surface"],
            "planes": p["planes"],
            "declared_hooks": p["expected_hooks"],
            "declared_status": p["status"],
            "source_activity": "CONFIRMED_ONLY_WHERE_LOCAL_STATE_DB_COUNTS_EXIST",
            "runtime_receipt": "NOT_FOUND",
            "canonical_authority_receipt": "NOT_FOUND",
            "read_after_write": "NOT_FOUND",
            "rollback_receipt": "NOT_FOUND",
            "verdict": "DECLARED_ONLY_OR_SOURCE_ACTIVITY_ONLY",
        })
    out = {
        "artifact_id": "mwp-producer-runtime-receipt-census-v1",
        "mwp_id": "MWP-UOSH-001",
        "status": "RUNTIME_RECEIPTS_MISSING_FAIL_CLOSED",
        "producer_count": len(rows),
        "runtime_receipts_verified": 0,
        "canonical_authority_receipts_verified": 0,
        "read_after_write_verified": 0,
        "rollback_receipts_verified": 0,
        "producers": rows,
        "writes_allowed": False,
        "next_action": "obtain one metadata-only live receipt per producer with principal/tenant/scope/provenance/correlation/idempotency/runtime path",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(OUT), "producer_count": len(rows), "runtime_receipts_verified": 0, "writes_allowed": False}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
