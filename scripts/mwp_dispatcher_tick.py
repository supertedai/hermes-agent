#!/usr/bin/env python3
"""Run the metadata-only dispatcher stage for the active MWP mission."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.dispatcher_adapter import Dispatcher
from agent.mwp_canonical_ingress import LeaseEvidence, authorize_autocoder
from agent.mwp_control_plane import Axis, ControlTask, TaskState
from agent.mwp_orchestrator_adapter import OrchestratorAdapter

SOURCE = ROOT / "docs/mwp-final-closeout-readback.json"
TARGET = ROOT / "docs/mwp-dispatcher-readback.json"


def _state(value: str) -> TaskState:
    value = str(value or "").upper()
    if value == "BLOCKED":
        return TaskState.BLOCKED
    if value in {"CONNECTED_READ_ONLY", "LIVE_VERIFIED", "COMPLETE"}:
        return TaskState.CLOSED
    return TaskState.READY


def _canonical_parent_lease(task_id: str) -> dict[str, object]:
    env = os.environ.copy()
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)
    env["HERMES_PROFILE"] = "default"
    try:
        completed = subprocess.run(
            ["hermes", "kanban", "show", task_id, "--json"],
            cwd=str(ROOT),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        payload = json.loads(completed.stdout)
        task = payload.get("task") or {}
        events = payload.get("events") or []
        has_claim = any(event.get("kind") == "claimed" for event in events)
        has_heartbeat = any(event.get("kind") == "heartbeat" for event in events)
        verified = task.get("status") == "running" and has_claim and has_heartbeat
        return {"verified": verified, "task": task, "events": events}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"verified": False, "blocker": f"kanban readback failed: {type(exc).__name__}"}


CHILD_TASK_IDS = {
    "git-deploy-daemon-status": "t_2b0cf534",
    "daemon-bl-health-alignment": "t_98303ce5",
    "world-model-hub-alignment": "t_febf599b",
    "chat-cortex-shared-readview": "t_a285ed6b",
    "lateral-agent-bus": "t_2e45934c",
    "asi-control-spine": "t_68e5d9d0",
}

READ_ONLY_LANES = frozenset(CHILD_TASK_IDS)


def _lease_from_readback(readback: dict[str, object], task_id: str) -> LeaseEvidence:
    task = readback.get("task") or {}
    events = readback.get("events") or []
    has_claim = any(event.get("kind") == "claimed" for event in events if isinstance(event, dict))
    has_heartbeat = any(event.get("kind") == "heartbeat" for event in events if isinstance(event, dict))
    claim_event = next((event for event in reversed(events) if isinstance(event, dict) and event.get("kind") == "claimed"), {})
    payload = claim_event.get("payload") or {}
    return LeaseEvidence(
        task_id=task_id,
        status=str(task.get("status") or ""),
        claimed=has_claim,
        heartbeat=has_heartbeat,
        lease_active=bool(payload.get("expires", 0)) and int(payload.get("expires", 0)) > int(__import__("time").time()),
    )


def _canonical_task_readback(task_id: str) -> dict[str, object]:
    env = os.environ.copy()
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)
    env["HERMES_PROFILE"] = "default"
    try:
        completed = subprocess.run(["hermes", "kanban", "show", task_id, "--json"], cwd=str(ROOT), env=env, check=True, capture_output=True, text=True, timeout=15)
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def run() -> dict[str, object]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    scope = payload.get("scope") or {}
    tasks = []
    for row in (payload.get("registry") or {}).get("rows", []):
        task_id = str(row.get("key") or "").strip()
        if not task_id:
            continue
        tasks.append(ControlTask(
            mwp_id=str(scope.get("installation_id") or "mwp"),
            case_id="mwp-closeout",
            task_id=task_id,
            principal_id=str(scope.get("user_id") or "owner"),
            axis=Axis.SYSTEM,
            state=_state(row.get("status")),
            scope=str(row.get("scope") or "mwp-closeout"),
            required_gate=str(row.get("gap") or ""),
            next_permitted_action=str(row.get("gap") or "continue local lane"),
        ))
    orchestrator = OrchestratorAdapter(tasks, parent_task_id="mwp-closeout-parent")
    parent_lease = _canonical_parent_lease("t_fe6a5950")
    dispatcher = Dispatcher(
        orchestrator,
        principal_id=str(scope.get("user_id") or "morten"),
        authority_check=lambda: bool(parent_lease.get("verified")),
    )
    ready = dispatcher.project_ready_lanes()
    lease = dispatcher.manage_lease()
    parent_evidence = _lease_from_readback(parent_lease, "t_fe6a5950")
    ingress = []
    for chip in ready:
        child_id = CHILD_TASK_IDS.get(chip.task_id)
        child_readback = _canonical_task_readback(child_id) if child_id else {}
        child_evidence = _lease_from_readback(child_readback, child_id or "") if child_id else None
        ingress.append(authorize_autocoder(
            task_id=chip.task_id,
            principal_id=str(scope.get("user_id") or "morten"),
            parent=parent_evidence,
            child=child_evidence,
            read_only=chip.task_id in READ_ONLY_LANES,
        ).as_dict())
    result = {
        "status": "RUNNING" if ready else lease.status,
        "lease": lease.as_dict(),
        "canonical_parent_lease": {
            "verified": bool(parent_lease.get("verified")),
            "task_id": "t_fe6a5950",
            "task_status": (parent_lease.get("task") or {}).get("status"),
        },
        "ready_lane_ids": [chip.task_id for chip in ready],
        "autocoder_ingress": ingress,
        "chips": [event for event in dispatcher.orchestrator.emit_events()],
        "metadata_only": True,
        "authority_verified": bool(parent_lease.get("verified")),
        "source": str(SOURCE.relative_to(ROOT)),
    }
    tmp = TARGET.with_suffix(TARGET.suffix + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, TARGET)
    print(json.dumps({"status": result["status"], "lease": lease.lease.value, "ready_lane_count": len(ready), "chip_count": len(result["chips"])}))
    return result


if __name__ == "__main__":
    run()
