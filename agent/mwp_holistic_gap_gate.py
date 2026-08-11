"""Executable metadata-only holistic MWP gap gate."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


GATES = (
    "G0_SCOPE_AND_BASELINE",
    "G1_INDUSTRY_BASELINE",
    "G2_SOTA_REVIEW",
    "G3_ASI_CUTTING_EDGE_REVIEW",
    "G4_CROSS_PLANE_COMPATIBILITY",
    "G5_TEST_AND_MEASURE",
    "G6_LIVE_EVIDENCE",
    "G7_CLOSEOUT_DECISION",
)
PLANES = ("neo4j", "qdrant", "gnn", "hermes", "surface")


def evaluate_holistic_gap_gate(
    *,
    scope: Mapping[str, Any],
    gates: Mapping[str, Mapping[str, Any]],
    cross_plane: Mapping[str, Mapping[str, Any]],
    writes_allowed: bool = False,
) -> dict[str, Any]:
    """Evaluate G0-G7 without changing files, stores or runtime state."""
    blockers: list[str] = []
    partial: list[str] = []
    for gate in GATES:
        record = gates.get(gate, {})
        status = record.get("status")
        if status == "COMPLETE":
            continue
        if status in {"PARTIAL", "OPEN", "UNVERIFIED"}:
            partial.append(f"{gate}:{status}")
        else:
            blockers.append(f"{gate}:missing_or_blocked")
    if not scope.get("target") or not scope.get("baseline"):
        blockers.append("G0_SCOPE_AND_BASELINE:target_or_baseline_missing")
    for plane in PLANES:
        status = cross_plane.get(plane, {}).get("status")
        if status != "COMPLETE":
            partial.append(f"G4:{plane}:{status or 'missing'}")
    if writes_allowed:
        blockers.append("writes_allowed_must_remain_false_for_metadata_gate")
    if blockers:
        verdict = "BLOCKED"
    elif partial:
        verdict = "PARTIAL"
    else:
        verdict = "COMPLETE"
    return {
        "verdict": verdict,
        "blockers": blockers,
        "partial": partial,
        "gates_checked": list(GATES),
        "cross_plane_checked": list(PLANES),
        "writes_performed": False,
        "raw_payload_included": False,
    }
