"""Opt-in P2 write preflight; never performs a write."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent.mwp_cross_surface_truth import (
    TruthVerdict,
    validate_strict_truth_receipts,
)


def validate_p2_write_preflight(
    envelope: Mapping[str, Any],
    canonical: Mapping[str, Any] | None,
    outbox: Mapping[str, Any] | None,
    projections: Sequence[Mapping[str, Any]],
    *,
    required_surfaces: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a metadata-only P2 verdict; callers must gate writes on COMPLETE."""
    verdict, blockers = validate_strict_truth_receipts(
        envelope,
        canonical,
        outbox,
        projections,
        required_surfaces=required_surfaces,
    )
    return {
        "verdict": verdict,
        "blockers": list(blockers),
        "write_allowed": verdict == TruthVerdict.COMPLETE,
        "raw_payload_included": False,
    }
