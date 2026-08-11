"""Fail-closed ExperimentRun receipt for MWP autonomous experiments."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class Axis(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class RunStatus(StrEnum):
    PROPOSED = "PROPOSED"
    RUNNING = "RUNNING"
    KEEP = "KEEP"
    DISCARD = "DISCARD"
    BLOCKED = "BLOCKED"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class Provenance:
    source: str
    verified: bool = False
    source_commit: str = ""
    traceparent: str = ""


@dataclass(frozen=True)
class ExperimentRun:
    experiment_id: str
    goal_id: str
    axis: Axis
    status: RunStatus
    metric: str
    baseline: Any
    provenance: Provenance
    bl_ref: str = ""
    principal_id: str = ""
    agent_id: str = ""
    after: Any = None
    change_ref: str = ""
    rollback_ref: str = ""
    reviewer_verdict: str = "PENDING"
    outcome: str = ""
    learning_event_ref: str = ""
    budget_seconds: float | None = None
    parallelism: int | None = None
    evidence: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        for name in ("experiment_id", "goal_id", "metric"):
            if not getattr(self, name).strip():
                errors.append(f"{name} is required")
        if not self.provenance.source.strip():
            errors.append("provenance.source is required")
        if self.budget_seconds is not None and self.budget_seconds < 0:
            errors.append("budget_seconds must be non-negative")
        if self.parallelism is not None and self.parallelism < 1:
            errors.append("parallelism must be positive")
        if self.status in {RunStatus.KEEP, RunStatus.DISCARD} and self.after is None:
            errors.append("KEEP/DISCARD requires an after measurement")
        if self.status is RunStatus.KEEP and not self.rollback_ref.strip():
            errors.append("KEEP requires rollback_ref")
        if self.status is RunStatus.KEEP and self.reviewer_verdict != "PASS":
            errors.append("KEEP requires reviewer_verdict=PASS")
        return tuple(errors)

    def require_valid(self) -> "ExperimentRun":
        errors = self.validate()
        if errors:
            raise ValueError("invalid ExperimentRun: " + "; ".join(errors))
        return self

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["axis"] = self.axis.value
        data["status"] = self.status.value
        return data
