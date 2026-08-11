"""Fail-closed promotion gate for canonical BL-3935 receipts.

This is deliberately read-only. It never copies train.py, commits, deploys or
writes to the .12 authority. A separate owner/reviewer action is required for
any landing.
"""
from __future__ import annotations

import argparse
import json
import math
import shlex
import subprocess
from typing import Mapping


REVIEW_READY = "REVIEW_READY"
OWNER_GATE = "OWNER_GATE"


def _rollback_ref(receipt: Mapping[str, object]) -> str:
    explicit = receipt.get("rollback_ref")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    provenance = receipt.get("provenance")
    if isinstance(provenance, list):
        for item in provenance:
            if isinstance(item, str) and item.startswith("/tmp/autoresearch-runs/") and item.endswith("/train.py"):
                return item
    return ""


def evaluate_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    blockers: list[str] = []
    if not isinstance(receipt, Mapping):
        return {"experiment_id": "", "status": OWNER_GATE, "blockers": ["receipt is not an object"], "side_effects": "none"}
    if receipt.get("bl") != "BL-3935":
        blockers.append("wrong or missing BL-3935")
    if receipt.get("decision") != "promote_candidate":
        blockers.append("receipt is not promote_candidate")
    if receipt.get("reviewer") != "PASS":
        blockers.append("canonical reviewer PASS missing")
    candidate_commit = receipt.get("candidate_commit")
    if not isinstance(candidate_commit, str) or not candidate_commit.strip():
        blockers.append("candidate provenance missing")
    value = receipt.get("val_bpb_observed")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        blockers.append("measured val_bpb missing")
    rollback_ref = _rollback_ref(receipt)
    if not rollback_ref:
        blockers.append("rollback_ref missing")
    return {
        "experiment_id": receipt.get("experiment_id", ""),
        "status": REVIEW_READY if not blockers else OWNER_GATE,
        "blockers": blockers,
        "rollback_ref": rollback_ref,
        "side_effects": "none",
    }


def remote_receipts(host: str, path: str) -> list[dict[str, object]]:
    command = f"tail -n 200 -- {shlex.quote(path)} 2>/dev/null || true"
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    out = []
    for line in proc.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="box12")
    parser.add_argument("--receipts", default="/home/byopus/external/BL-3923/experiment_receipts.jsonl")
    parser.add_argument("--experiment-id", default="")
    args = parser.parse_args()
    receipts = remote_receipts(args.host, args.receipts)
    if args.experiment_id:
        receipts = [r for r in receipts if r.get("experiment_id") == args.experiment_id]
    result = [evaluate_receipt(receipt) for receipt in receipts if receipt.get("decision") == "promote_candidate"]
    print(json.dumps({"status": "READ_ONLY_PROMOTION_GATE", "candidates": result, "side_effects": "none"}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
