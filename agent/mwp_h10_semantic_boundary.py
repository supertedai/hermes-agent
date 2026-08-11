"""Fail-closed semantic classification for H10 TheoryHomeRecords."""
from __future__ import annotations

from typing import Any, Mapping


class H10Verdict(str):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED_SEMANTIC_CLASSIFICATION"
    UNCLASSIFIED = "UNCLASSIFIED"


LAYERS = {"THEORY", "ARCHITECTURE_INTENT", "CAPABILITY_DECLARATION", "LIVE_RUNTIME_EVIDENCE", "ROADMAP_PROPOSAL", "SUPPORTING_ARTIFACT", "METHODOLOGY", "PREDICTION_ARTIFACT", "EVALUATION_ARTIFACT"}
CLAIMS = {"THEORY_CLAIM", "HYPOTHESIS", "PREDICTION", "EVIDENCE_INTERNAL", "EVIDENCE_EXTERNAL", "VALIDATION_PENDING", "VALIDATED", "FALSIFIED", "METHODOLOGY", "ONTOLOGY", "UNCLASSIFIED"}
RUNTIME = {"NOT_APPLICABLE", "DECLARED_ONLY", "PROPOSED_NOT_LIVE", "LIVE_UNVERIFIED", "LIVE_VERIFIED", "STALE", "RETIRED"}
_REQUIRED = ("record_id", "package_id", "home_class", "record_layer", "claim_status", "runtime_status", "source_ref", "provenance_ref", "owner_id", "review_status")


def validate_theory_home_record(record: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    missing = tuple(k for k in _REQUIRED if not str(record.get(k) or "").strip())
    if missing:
        return H10Verdict.UNCLASSIFIED, tuple(f"missing:{k}" for k in missing)
    if record["record_layer"] not in LAYERS:
        return H10Verdict.BLOCKED, ("invalid:record_layer",)
    if record["claim_status"] not in CLAIMS:
        return H10Verdict.BLOCKED, ("invalid:claim_status",)
    if record["runtime_status"] not in RUNTIME:
        return H10Verdict.BLOCKED, ("invalid:runtime_status",)
    if record["runtime_status"] == "LIVE_VERIFIED" and not record.get("runtime_receipt_ref"):
        return H10Verdict.BLOCKED, ("live_verified_without_runtime_receipt",)
    if record["claim_status"] == "VALIDATED" and not record.get("evaluation_receipt_ref"):
        return H10Verdict.BLOCKED, ("validated_without_evaluation_receipt",)
    if record["review_status"] not in {"PENDING", "REVIEWED", "APPROVED", "REJECTED"}:
        return H10Verdict.BLOCKED, ("invalid:review_status",)
    return H10Verdict.COMPLETE, ()
