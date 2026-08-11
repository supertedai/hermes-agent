#!/usr/bin/env python3
"""Collect bounded, metadata-only authority receipts from canonical box12."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/mwp-remote-authority-readback.json"

REMOTE = r'''cd /home/byopus/AGI && set -a && . ./.env && set +a && DASH_REPO=/home/byopus/AGI NEO4J_URL=http://127.0.0.1:7474 python3 tools/world_model_hub.py --state'''
REMOTE_LATERAL = r'''python3 -c 'import urllib.request; r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8010/lateral-bus/status",headers={"X-User-ID":"morten"}),timeout=20); print(r.read().decode())' '''


def run() -> dict[str, object]:
    result: dict[str, object] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "host": "box12",
        "metadata_only": True,
        "graph_or_obsidian_write": False,
    }
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "box12", REMOTE],
            cwd=str(ROOT), capture_output=True, text=True, timeout=90, check=True,
        )
        state = json.loads(proc.stdout)
        errors = [v for v in state.values() if isinstance(v, dict) and "__error__" in v]
        result["world_model"] = {
            "status": "VERIFIED" if not errors else "BLOCKED",
            "domains": len(state.get("domains", [])) if isinstance(state.get("domains"), list) else None,
            "experiences": state.get("total_experiences"),
            "cross_domain_links": state.get("cross_domain_links"),
            "patterns": state.get("patterns"),
            "errors": errors,
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result["world_model"] = {"status": "BLOCKED", "error": f"{type(exc).__name__}: {exc}"}
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "box12", REMOTE_LATERAL],
            cwd=str(ROOT), capture_output=True, text=True, timeout=45, check=True,
        )
        result["lateral_bus"] = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result["lateral_bus"] = {"status": "BLOCKED", "error": f"{type(exc).__name__}: {exc}"}
    result["next_action"] = "continue local lanes; keep remote authority read-only until every receipt is fresh"
    tmp = TARGET.with_suffix(TARGET.suffix + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, TARGET)
    print(json.dumps({"host": result["host"], "world_model": result["world_model"], "lateral_bus": result["lateral_bus"], "metadata_only": True}))
    return result


if __name__ == "__main__":
    run()
