"""Read-only authority readback for the canonical .12 BL-3935 loop."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter

DEFAULT_HOST = "box12"
DEFAULT_ROOT = "/home/byopus/external/BL-3923"


def remote(host: str, command: str) -> str:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or f"ssh failed with {proc.returncode}")
    return proc.stdout.strip()


def readback(host: str = DEFAULT_HOST, root: str = DEFAULT_ROOT) -> dict[str, object]:
    receipt_path = f"{root}/experiment_receipts.jsonl"
    autoresearch = f"{root}/autoresearch"
    script = "/home/byopus/run_autoresearch_loop.sh"
    gpu = remote(host, "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader")
    head = remote(host, f"if [ -d {autoresearch}/.git ]; then git -C {autoresearch} rev-parse HEAD; else sha256sum {autoresearch}/train.py | cut -d' ' -f1; fi")
    dirty = int(remote(host, f"if [ -d {autoresearch}/.git ]; then git -C {autoresearch} status --porcelain | wc -l; else echo 0; fi"))
    cron = remote(host, "(crontab -l 2>/dev/null || true) | grep -E 'autoresearch_loop|BL-3935' || true")
    receipts_raw = remote(host, f"tail -n 200 {receipt_path} 2>/dev/null || true")
    receipts = []
    for line in receipts_raw.splitlines():
        try:
            receipts.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    decisions = Counter(str(item.get("decision", "unknown")) for item in receipts)
    return {
        "status": "AUTHORITY_READBACK",
        "host": host,
        "root": root,
        "autoresearch_head": head,
        "dirty_entries": dirty,
        "gpu": gpu.splitlines(),
        "cron": cron,
        "receipt_count_sampled": len(receipts),
        "decision_counts_sampled": dict(decisions),
        "canonical_wrapper": script,
        "training_started_by_readback": False,
        "side_effects": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(readback(args.host, args.root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
