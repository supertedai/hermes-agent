"""Fail-closed canonical ingress guard for MWP autocoding.

Autocoder execution is permitted only when the canonical parent and child
Kanban leases are both verified and a principal is present. This module does
not claim tasks, spawn workers, or perform external writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IngressStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class LeaseEvidence:
    task_id: str
    status: str
    claimed: bool
    heartbeat: bool
    lease_active: bool

    @property
    def verified(self) -> bool:
        return bool(self.task_id and self.status == "running" and self.claimed and self.heartbeat and self.lease_active)


@dataclass(frozen=True)
class IngressReadback:
    status: IngressStatus
    task_id: str
    principal_id: str
    blocker: str = ""
    next_action: str = ""
    parent: LeaseEvidence | None = None
    child: LeaseEvidence | None = None
    execution_mode: str = "mutating"

    @property
    def executor_allowed(self) -> bool:
        return self.status is IngressStatus.READY

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "task_id": self.task_id,
            "principal_id": self.principal_id,
            "executor_allowed": self.executor_allowed,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "parent_lease_verified": bool(self.parent and self.parent.verified),
            "child_lease_verified": bool(self.child and self.child.verified),
            "execution_mode": self.execution_mode,
        }


def authorize_autocoder(
    *,
    task_id: str,
    principal_id: str,
    parent: LeaseEvidence | None,
    child: LeaseEvidence | None,
    read_only: bool = False,
) -> IngressReadback:
    if not principal_id.strip():
        return IngressReadback(IngressStatus.BLOCKED, task_id, principal_id, "principal is missing", "bind an authenticated Hermes principal")
    if read_only:
        return IngressReadback(
            IngressStatus.READY,
            task_id,
            principal_id,
            blocker="",
            next_action="metadata-only lane may proceed without a write lease",
            parent=parent,
            child=child,
            execution_mode="read_only",
        )
    if parent is None or not parent.verified:
        return IngressReadback(IngressStatus.BLOCKED, task_id, principal_id, "parent Kanban lease is not verified", "claim and heartbeat the canonical parent")
    if child is None or not child.verified:
        return IngressReadback(IngressStatus.BLOCKED, task_id, principal_id, "child Kanban lease is not verified", "claim and heartbeat the canonical child lane")
    return IngressReadback(IngressStatus.READY, task_id, principal_id, parent=parent, child=child)
