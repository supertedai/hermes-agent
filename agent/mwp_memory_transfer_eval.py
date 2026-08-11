"""Deterministic memory-transfer evaluation contract.

The evaluator consumes episode-level metadata, not raw memory or model output.
It is suitable for synthetic shadow fixtures and later live adapter readback.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EpisodeResult:
    case_id: str
    memory_enabled: bool
    success: bool
    retrieved_relevant: bool
    retrieved_irrelevant: bool
    saved: bool
    updated: bool
    cost_ms: float


@dataclass(frozen=True)
class MemoryEvalReport:
    status: str
    memory_on_success: float
    memory_off_success: float
    transfer_gain: float
    interference_rate: float
    pathway_compliance: float
    cost_delta_ms: float
    promotion_eligible: bool
    labels: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "memory_on_success": self.memory_on_success,
            "memory_off_success": self.memory_off_success,
            "transfer_gain": self.transfer_gain,
            "interference_rate": self.interference_rate,
            "pathway_compliance": self.pathway_compliance,
            "cost_delta_ms": self.cost_delta_ms,
            "promotion_eligible": self.promotion_eligible,
            "labels": list(self.labels),
        }


def evaluate(results: list[EpisodeResult], *, max_interference: float = 0.10) -> MemoryEvalReport:
    if not results:
        raise ValueError("at least one episode result is required")
    on = [r for r in results if r.memory_enabled]
    off = [r for r in results if not r.memory_enabled]
    if not on or not off:
        raise ValueError("paired memory-on and memory-off results are required")
    on_success = sum(r.success for r in on) / len(on)
    off_success = sum(r.success for r in off) / len(off)
    interference = sum(r.retrieved_irrelevant for r in on) / len(on)
    pathway = sum(r.saved and r.updated for r in on) / len(on)
    cost_delta = (sum(r.cost_ms for r in on) / len(on)) - (sum(r.cost_ms for r in off) / len(off))
    eligible = on_success > off_success and interference <= max_interference and pathway >= 0.5
    return MemoryEvalReport(
        status="SYNTHETIC_SHADOW_FIXTURE",
        memory_on_success=on_success,
        memory_off_success=off_success,
        transfer_gain=on_success - off_success,
        interference_rate=interference,
        pathway_compliance=pathway,
        cost_delta_ms=cost_delta,
        promotion_eligible=eligible,
        labels=("synthetic_shadow_fixture", "derived_metric", "not_live_agent_effect"),
    )
