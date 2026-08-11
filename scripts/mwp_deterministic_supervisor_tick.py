#!/usr/bin/env python3
"""Deterministic durable MWP supervisor tick (fail-closed)."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "HERMES_PROFILE": "default"}
ENV.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)


def run(label: str, argv: list[str], timeout: int = 180) -> dict[str, object]:
    try:
        p = subprocess.run(argv, cwd=ROOT, env=ENV, text=True, capture_output=True, timeout=timeout)
        already_active = label == "claim" and "status=running lock=" in p.stderr
        return {"label": label, "exit_code": p.returncode, "ok": p.returncode == 0 or already_active,
                "state": "already_active" if already_active else ("ok" if p.returncode == 0 else "error"),
                "stdout": p.stdout[-1200:], "stderr": p.stderr[-800:]}
    except Exception as exc:
        return {"label": label, "exit_code": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _closeout_allows_claim(result: dict[str, object]) -> bool:
    """Only claim after a verified, non-blocked closeout readback."""
    if not result.get("ok"):
        return False
    try:
        payload = json.loads(str(result.get("stdout", "")))
    except (TypeError, ValueError):
        return False
    return payload.get("status") == "COMPLETE" and int(payload.get("blocker_count", 0)) == 0


def main() -> int:
    # Readback first. A blocked or malformed closeout must never create a lease.
    preflight = [
        ("remote_receipt", ["python3", "scripts/mwp_remote_receipt_tick.py"]),
        ("topology", ["python3", "scripts/mwp_topology_tick.py"]),
        ("closeout", ["python3", "scripts/mwp_closeout_tick.py"]),
    ]
    results = [run(label, argv) for label, argv in preflight]
    closeout = next(r for r in results if r["label"] == "closeout")
    if not _closeout_allows_claim(closeout):
        results.append({"label": "claim", "exit_code": None, "ok": True,
                        "state": "blocked_no_claim", "stdout": "",
                        "stderr": "closeout is not COMPLETE; no claim, heartbeat, or dispatch"})
        print(json.dumps({
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_NO_CLAIM",
            "parent_task": "t_fe6a5950",
            "stages": results,
            "failed_stages": [r["label"] for r in results if not r["ok"]],
            "next_action": "owner evidence required; rerun readback without creating a lease",
        }, ensure_ascii=False))
        return 0

    stages = [
        ("claim", ["hermes", "kanban", "claim", "t_fe6a5950", "--ttl", "900"]),
        ("heartbeat", ["hermes", "kanban", "heartbeat", "t_fe6a5950", "--note", "deterministic persistent MWP supervisor tick"]),
        ("orchestrator", ["python3", "scripts/mwp_orchestrator_tick.py"]),
        ("dispatcher", ["python3", "scripts/mwp_dispatcher_tick.py"]),
        ("kanban_dispatch", ["hermes", "kanban", "dispatch", "--max", "6", "--failure-limit", "2", "--json"]),
    ]
    results.extend(run(label, argv) for label, argv in stages)
    failed = [r["label"] for r in results if not r["ok"]]
    print(json.dumps({"recorded_at": datetime.now(timezone.utc).isoformat(),
                      "status": "RUNNING" if not failed else "RUNNING_WITH_STAGE_ERRORS",
                      "parent_task": "t_fe6a5950", "stages": results,
                      "failed_stages": failed,
                      "next_action": "next scheduled tick; blocked lanes remain parked with owner/evidence/next_action"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
