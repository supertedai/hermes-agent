"""Adaptive, metadata-only agent capability/liveness projection for MWP.

The registry is an input, not an authority for live execution. This module never
starts agents, claims tasks, selects a model provider for execution, or writes a
registry. It only projects safe candidate metadata and fails closed when no
fresh, capability-bearing candidate exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class ProjectionStatus(str):
    LIVE_VERIFIED = "LIVE_VERIFIED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    DECLARED_ONLY = "DECLARED_ONLY"
    NO_CAPABILITY_EVIDENCE = "NO_CAPABILITY_EVIDENCE"


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    kind: str = ""
    model: str = ""
    runtime: str = ""
    last_active: str | None = None
    capabilities: tuple[str, ...] = ()
    superseded: str | None = None
    source: str = "registry"


@dataclass(frozen=True)
class AgentProjection:
    agent_id: str
    kind: str
    model: str
    runtime: str
    status: str
    freshness_seconds: int | None
    capability_count: int
    capabilities: tuple[str, ...]
    source: str
    superseded: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "kind": self.kind,
            "model": self.model,
            "runtime": self.runtime,
            "status": self.status,
            "freshness_seconds": self.freshness_seconds,
            "capability_count": self.capability_count,
            "capabilities": list(self.capabilities),
            "source": self.source,
            "superseded": self.superseded,
        }


def _age_seconds(value: str | None, now: datetime) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((now - parsed.astimezone(timezone.utc)).total_seconds()))
    except (TypeError, ValueError):
        return None


def project_agents(
    records: Iterable[AgentRecord],
    *,
    now: datetime,
    freshness_seconds: int = 900,
) -> tuple[AgentProjection, ...]:
    """Project registry records without upgrading declarations into live state."""
    if freshness_seconds < 0:
        raise ValueError("freshness_seconds must be non-negative")
    result: list[AgentProjection] = []
    for record in records:
        age = _age_seconds(record.last_active, now)
        if record.superseded:
            status = ProjectionStatus.DECLARED_ONLY
        elif not record.capabilities:
            status = ProjectionStatus.NO_CAPABILITY_EVIDENCE
        elif age is None:
            status = ProjectionStatus.UNKNOWN
        elif age > freshness_seconds:
            status = ProjectionStatus.STALE
        else:
            status = ProjectionStatus.LIVE_VERIFIED
        result.append(AgentProjection(
            agent_id=record.agent_id,
            kind=record.kind,
            model=record.model,
            runtime=record.runtime,
            status=status,
            freshness_seconds=age,
            capability_count=len(record.capabilities),
            capabilities=tuple(sorted(record.capabilities)),
            source=record.source,
            superseded=bool(record.superseded),
        ))
    return tuple(sorted(result, key=lambda item: item.agent_id))


def records_from_registry_payload(payload: Mapping[str, Any]) -> tuple[AgentRecord, ...]:
    """Convert the adaptive registry snapshot into projection inputs."""
    raw_agents = payload.get("agents", [])
    if not isinstance(raw_agents, list):
        raise ValueError("registry payload agents must be a list")
    records: list[AgentRecord] = []
    for raw in raw_agents:
        if not isinstance(raw, Mapping) or not str(raw.get("id") or "").strip():
            continue
        skills = raw.get("skills") or []
        capabilities = tuple(
            sorted({str(item.get("domain")) for item in skills if isinstance(item, Mapping) and item.get("domain")})
        )
        records.append(AgentRecord(
            agent_id=str(raw["id"]),
            kind=str(raw.get("kind") or ""),
            model=str(raw.get("model") or ""),
            runtime=str(raw.get("runtime") or ""),
            last_active=raw.get("last_active"),
            capabilities=capabilities,
            superseded=str(raw.get("superseded") or "") or None,
            source="agents.json",
        ))
    return tuple(records)


def select_candidates(
    projections: Iterable[AgentProjection],
    *,
    capability: str,
) -> tuple[AgentProjection, ...]:
    """Return only fresh live candidates; empty means the lane is blocked."""
    wanted = capability.strip().lower()
    if not wanted:
        raise ValueError("capability is required")
    return tuple(
        item for item in projections
        if item.status == ProjectionStatus.LIVE_VERIFIED
        and not item.superseded
        and wanted in {capability.lower() for capability in item.capabilities}
    )


def metadata_readback(projections: Iterable[AgentProjection]) -> dict[str, Any]:
    rows = tuple(projections)
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
    return {
        "agent_count": len(rows),
        "status_counts": dict(sorted(by_status.items())),
        "candidate_count": sum(1 for row in rows if row.status == ProjectionStatus.LIVE_VERIFIED and not row.superseded),
        "raw_payload_included": False,
    }
