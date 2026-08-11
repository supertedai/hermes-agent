#!/usr/bin/env python3
"""Create a fail-closed holistic gate input skeleton for a workflow step."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.mwp_holistic_gap_gate import GATES, PLANES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = {
        "scope": {"target": args.target, "baseline": args.baseline},
        "gates": {gate: {"status": "OPEN", "evidence": []} for gate in GATES},
        "cross_plane": {plane: {"status": "OPEN", "evidence": []} for plane in PLANES},
        "writes_allowed": False,
        "generated_by": "scripts/new_mwp_holistic_gap_input.py",
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "initial_verdict": "PARTIAL", "writes_allowed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
