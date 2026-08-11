#!/usr/bin/env python3
"""Run the metadata-only holistic MWP gap gate against a JSON input."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.mwp_holistic_gap_gate import evaluate_holistic_gap_gate


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"error": "usage: run_mwp_holistic_gap_gate.py INPUT.json"}))
        return 2
    path = Path(argv[1])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = evaluate_holistic_gap_gate(
            scope=payload.get("scope", {}),
            gates=payload.get("gates", {}),
            cross_plane=payload.get("cross_plane", {}),
            writes_allowed=bool(payload.get("writes_allowed", False)),
        )
    except Exception as exc:
        print(json.dumps({"verdict": "BLOCKED", "blockers": [f"input:{exc}"], "writes_performed": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verdict"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
