"""External MWP pre-claim policy for the canonical Hermes Kanban dispatcher.

Non-MWP tasks are deliberately left to existing Hermes policy. A task is in
MWP scope only when it carries the explicit ``MWP-UOSH-001`` marker in its id,
title, body or tenant. MWP tasks must have an explicit verified evidence event
before they may be claimed. This module is a policy adapter, not a task store.
"""
from __future__ import annotations

import json
from typing import Any

from agent.mwp_autonomy_adapter import mission_readback_from_control_task
from agent.mwp_control_plane import Axis, ControlTask, TaskState

MWP_MARKER = "MWP-UOSH-001"
VERIFIED_EVENT = "mwp_evidence_verified"


def _is_mwp_task(task: Any) -> bool:
    fields = (
        getattr(task, "id", ""),
        getattr(task, "title", ""),
        getattr(task, "body", ""),
        getattr(task, "tenant", ""),
    )
    return any(MWP_MARKER in str(value or "") for value in fields)


def _task_state(status: str) -> TaskState:
    return {
        "ready": TaskState.READY,
        "review": TaskState.REVIEW,
        "blocked": TaskState.BLOCKED,
        "scheduled": TaskState.PLANNED,
        "running": TaskState.RUNNING,
        "done": TaskState.CLOSED,
    }.get(str(status).lower(), TaskState.PLANNED)


def _verified_refs(conn: Any, task_id: str) -> tuple[str, ...]:
    refs: list[str] = []
    for row in conn.execute(
        "SELECT id, payload FROM task_events WHERE task_id = ? AND kind = ?",
        (task_id, VERIFIED_EVENT),
    ):
        payload = row[1] or "{}"
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            data = {}
        ref = str(data.get("evidence_ref") or f"event:{row[0]}").strip()
        if ref:
            refs.append(ref)
    return tuple(dict.fromkeys(refs))


def _control_task(task: Any) -> ControlTask:
    return ControlTask(
        mwp_id=MWP_MARKER,
        case_id="CASE-AUTONOMY-00",
        task_id=str(task.id),
        principal_id=str(task.tenant or task.created_by or "system"),
        axis=Axis.SYSTEM,
        state=_task_state(task.status),
        scope=str(task.workspace_path or "kanban/mwp"),
        evidence_refs=(),
        rollback_ref=str(getattr(task, "result", "") or ""),
        model_role=str(task.assignee or ""),
    )


def preclaim_policy(conn: Any, task_id: str, board: str | None = None) -> bool | tuple[bool, str]:
    """Return a dispatcher-compatible verdict before ``claim_task``.

    ``True`` means the existing dispatcher may proceed. A tuple beginning with
    ``False`` blocks the claim and records the reason in the dispatch result.
    """
    from hermes_cli import kanban_db

    task = kanban_db.get_task(conn, task_id)
    if task is None or not _is_mwp_task(task):
        return True
    verified = _verified_refs(conn, task_id)
    readback = mission_readback_from_control_task(
        _control_task(task),
        {task_id: _control_task(task)},
        verified_evidence_refs=verified,
        required_evidence_refs=("mwp:evidence",),
    )
    if not readback.permitted:
        reason = "; ".join(readback.blockers) or "MWP autonomy gate blocked"
        return False, reason
    return True
