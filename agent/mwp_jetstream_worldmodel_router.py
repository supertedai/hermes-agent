"""Metadata-only Jetstream -> world model -> Cortex/domain routing contract.

This module decides *where* a Jetstream signal may be projected. It never
fetches, writes graph/memory, broadcasts raw payloads, or grants runtime
authority. Existing Jetstream and world_model_hub writers remain canonical.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ProjectionStatus(str, Enum):
    ROUTE_TO_CORTEX_AND_DOMAINS = "ROUTE_TO_CORTEX_AND_DOMAINS"
    ROUTE_TO_CORTEX_ONLY = "ROUTE_TO_CORTEX_ONLY"
    QUARANTINE = "QUARANTINE"
    DROP_STALE = "DROP_STALE"


@dataclass(frozen=True)
class JetstreamSignal:
    signal_id: str
    source_id: str
    domain: str
    topic: str
    entropy: float
    freshness: str
    provenance_ref: str
    payload_ref: str
    gap_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    injection_checked: bool = False

    def __post_init__(self) -> None:
        required = {
            "signal_id": self.signal_id,
            "source_id": self.source_id,
            "domain": self.domain,
            "topic": self.topic,
            "freshness": self.freshness,
            "provenance_ref": self.provenance_ref,
            "payload_ref": self.payload_ref,
        }
        missing = [key for key, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("missing Jetstream signal fields: " + ", ".join(missing))
        if not 0.0 <= float(self.entropy) <= 1.0:
            raise ValueError("entropy must be between 0 and 1")
        if any(not str(ref).strip() for ref in (*self.gap_refs, *self.evidence_refs)):
            raise ValueError("empty gap/evidence refs are not allowed")


@dataclass(frozen=True)
class ProjectionDecision:
    signal_id: str
    status: ProjectionStatus
    cortex_target: str | None
    domain_targets: tuple[str, ...]
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    metadata_only: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "signal_id": self.signal_id,
            "status": self.status.value,
            "cortex_target": self.cortex_target,
            "domain_targets": list(self.domain_targets),
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "metadata_only": self.metadata_only,
        }


def route_signal(
    signal: JetstreamSignal,
    *,
    domain_agents: Iterable[str] = (),
    entropy_floor: float = 0.70,
    max_age_status: str = "FRESH",
) -> ProjectionDecision:
    """Route a signal by entropy/gap relevance with fail-closed provenance."""
    blockers: list[str] = []
    reasons: list[str] = []
    domain_targets = tuple(dict.fromkeys(str(a) for a in domain_agents if str(a).strip()))
    high_entropy = signal.entropy >= entropy_floor
    has_gap = bool(signal.gap_refs)
    fresh = signal.freshness == max_age_status

    if not signal.injection_checked:
        blockers.append("injection scan not verified")
    if not fresh:
        return ProjectionDecision(
            signal.signal_id,
            ProjectionStatus.DROP_STALE,
            None,
            (),
            ("signal is not fresh",),
            tuple(blockers),
        )
    if not signal.provenance_ref or not signal.payload_ref:
        blockers.append("provenance/payload reference missing")
    if blockers:
        return ProjectionDecision(
            signal.signal_id,
            ProjectionStatus.QUARANTINE,
            None,
            (),
            tuple(reasons),
            tuple(blockers),
        )
    if high_entropy:
        reasons.append("entropy threshold exceeded")
    if has_gap:
        reasons.append("one or more KnowledgeGap refs present")
    if not (high_entropy or has_gap):
        return ProjectionDecision(
            signal.signal_id,
            ProjectionStatus.ROUTE_TO_CORTEX_ONLY,
            "Cortex/world_model_hub",
            (),
            ("no high-entropy or gap trigger for domain fan-out",),
            (),
        )
    return ProjectionDecision(
        signal.signal_id,
        ProjectionStatus.ROUTE_TO_CORTEX_AND_DOMAINS,
        "Cortex/world_model_hub",
        domain_targets,
        tuple(reasons),
        (),
    )
