"""Consent-first Faber -> Hermes TUI/cron suggestion bridge.

This is deliberately not a job engine. It writes only to the existing
``cron.suggestions`` surface; Morten must accept the suggestion before
``cron.jobs.create_job`` is called.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from cron.suggestions import add_suggestion, get_suggestion



@dataclass(frozen=True)
class FaberJobProposal:
    """Canonical consent-first proposal schema; not a running job."""

    goal_id: str
    title: str
    description: str
    bl_ref: str
    cad_ref: str
    adr_ref: str
    risk: str
    rollback: str
    job_spec: Mapping[str, Any]
    dedup_key: str

    def submit(self) -> dict[str, Any] | None:
        return propose_faber_job(**asdict(self))


def propose_faber_job(
    *,
    goal_id: str,
    title: str,
    description: str,
    bl_ref: str,
    cad_ref: str,
    adr_ref: str,
    risk: str,
    rollback: str,
    job_spec: Mapping[str, Any],
    dedup_key: str,
) -> dict[str, Any] | None:
    """Create a pending Faber proposal; never creates/runs a job directly."""
    required = {
        "goal_id": goal_id,
        "bl_ref": bl_ref,
        "cad_ref": cad_ref,
        "adr_ref": adr_ref,
        "risk": risk,
        "rollback": rollback,
    }
    if any(not str(value).strip() for value in required.values()):
        raise ValueError("goal, BL, CAD, ADR, risk and rollback are required")
    if not title.strip() or not description.strip() or not dedup_key.strip():
        raise ValueError("title, description and dedup_key are required")
    if bool(job_spec.get("act") or job_spec.get("auto_start")):
        raise PermissionError("Faber egress cannot propose autonomous ACT/start")
    enriched_description = (
        f"{description.strip()}\n\n"
        f"Faber provenance: goal_id={goal_id}; BL={bl_ref}; CAD={cad_ref}; "
        f"ADR={adr_ref}; risk={risk}; rollback={rollback}; trace_id={job_spec.get('trace_id', '') or '[unknown]'}."
    )
    return add_suggestion(
        title=title,
        description=enriched_description,
        source="faber",
        job_spec=dict(job_spec),
        dedup_key=f"faber:{goal_id}:{dedup_key}",
    )


def read_faber_tui_readback(ref: str) -> dict[str, Any]:
    """Read the existing TUI suggestion surface without creating/running a job."""
    record = get_suggestion(ref)
    if record is None:
        return {"found": False, "ref": ref, "surface": "cron.suggestions"}
    spec = dict(record.get("job_spec") or {})
    return {
        "found": True,
        "surface": "cron.suggestions",
        "id": record.get("id"),
        "source": record.get("source"),
        "status": record.get("status"),
        "dedup_key": record.get("dedup_key"),
        "trace_id": spec.get("trace_id"),
        "job_spec": spec,
        "created_at": record.get("created_at"),
        "resolved_at": record.get("resolved_at"),
    }
