#!/usr/bin/env python3
"""Emit one metadata-only mission/lane readback for the active MWP closeout."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.mwp_control_plane import Axis, ControlTask, TaskState
from agent.mwp_orchestrator_adapter import OrchestratorAdapter

SOURCE = ROOT / "docs/mwp-final-closeout-readback.json"
TARGET = ROOT / "docs/mwp-mission-orchestrator-readback.json"


def _state(value: str) -> TaskState:
    normalized = str(value or "").upper()
    if normalized == "BLOCKED":
        return TaskState.BLOCKED
    if normalized in {"CONNECTED_READ_ONLY", "LIVE_VERIFIED", "COMPLETE"}:
        return TaskState.CLOSED
    return TaskState.READY


def run() -> dict[str, object]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    registry = payload.get("registry") or {}
    tasks = []
    for row in registry.get("rows", []):
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        tasks.append(
            ControlTask(
                mwp_id=str(payload.get("scope", {}).get("installation_id", "mwp")),
                case_id="mwp-closeout",
                task_id=key,
                principal_id=str(payload.get("scope", {}).get("user_id", "owner")),
                axis=Axis.SYSTEM,
                state=_state(row.get("status", "")),
                scope=str(row.get("scope") or "mwp-closeout"),
                required_gate=str(row.get("gap") or ""),
                next_permitted_action=str(row.get("gap") or "continue local lanes"),
            )
        )
    adapter = OrchestratorAdapter(tasks, parent_task_id="mwp-closeout-parent")
    readbacks = adapter.calculate_states()
    result = {
        "status": adapter.parent_status().value,
        "ready_lane_ids": list(adapter.ready_lane_ids()),
        "readbacks": {key: value.as_dict() for key, value in readbacks.items()},
        "chips": list(adapter.emit_events()),
        "metadata_only": True,
        "source": str(SOURCE.relative_to(ROOT)),
    }
    tmp = TARGET.with_suffix(TARGET.suffix + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, TARGET)
    print(json.dumps({"status": result["status"], "ready_lane_count": len(result["ready_lane_ids"]), "chip_count": len(result["chips"])}))
    return result


if __name__ == "__main__":
    run()
