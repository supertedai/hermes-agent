"""Metadata-only topology context projection for Opus."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Mapping

_ALLOWED = {
    "architecture", "installation_id", "login_surface_id", "user_id", "agent_id",
    "observed_at", "expires_at", "overall_status", "status", "scope", "identity",
    "components", "runtime_hosts", "drift", "probe_status", "world_model",
    "memory", "learning", "cognitive", "cortex", "goals", "freshness", "source",
}
_FORBIDDEN = {"raw", "payload", "content", "secret", "token", "password", "credential"}


def _clean(value: Any, *, key: str = "") -> Any:
    lowered = key.lower()
    if lowered in _FORBIDDEN or any(word in lowered for word in _FORBIDDEN):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _clean(v, key=str(k)) for k, v in value.items() if str(k) in _ALLOWED or str(k) in {"name", "id", "status", "count", "reason", "next_action", "last_seen", "version", "hash", "added", "removed", "changed", "age_seconds", "ttl_seconds", "provenance"}}
    if isinstance(value, (list, tuple)):
        return [_clean(v, key=key) for v in value[:100]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def project_topology_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    projected = _clean(snapshot)
    projected["context_kind"] = "metadata-only-topology-readback"
    projected["projected_at"] = datetime.now(timezone.utc).isoformat()
    projected.setdefault("status", projected.get("overall_status", "UNVERIFIED"))
    projected.setdefault("freshness", {"status": "UNVERIFIED", "reason": "freshness evidence not supplied"})
    return projected


def load_topology_context(path: str | Path, *, now: datetime | None = None, ttl_seconds: int = 900, scope: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Load the heartbeat readback and inject only scoped, freshness-aware metadata."""
    current = now or datetime.now(timezone.utc)
    target = Path(path).expanduser()
    if not target.is_file():
        return project_topology_context({**(scope or {}), "status": "UNKNOWN", "freshness": {"status": "UNKNOWN", "reason": "topology readback missing"}})
    try:
        snapshot = json.loads(target.read_text(encoding="utf-8"))
        observed = datetime.fromisoformat(str(snapshot["recorded_at"]).replace("Z", "+00:00"))
        age = max(0.0, (current - observed).total_seconds())
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return project_topology_context({**(scope or {}), "status": "UNKNOWN", "freshness": {"status": "UNKNOWN", "reason": "topology readback invalid"}})
    fresh = age <= ttl_seconds
    merged = {**snapshot, **(scope or {})}
    merged["observed_at"] = snapshot.get("recorded_at")
    merged["expires_at"] = (observed.timestamp() + ttl_seconds)
    merged["freshness"] = {"status": "FRESH" if fresh else "STALE", "age_seconds": round(age, 3), "ttl_seconds": ttl_seconds, "last_seen": snapshot.get("recorded_at")}
    merged["status"] = "LIVE" if fresh else "STALE"
    return project_topology_context(merged)




def classify_topology_status(projected: Mapping[str, Any]) -> str:
    """Fail-closed classification for dynamic discovery readbacks."""
    freshness = projected.get("freshness", {})
    freshness_status = freshness.get("status") if isinstance(freshness, Mapping) else None
    if projected.get("status") == "UNKNOWN" or freshness_status == "UNKNOWN":
        return "UNKNOWN"
    if projected.get("status") == "STALE" or freshness_status == "STALE":
        return "STALE"
    drift = projected.get("drift", {})
    if isinstance(drift, Mapping) and any(drift.get(key) for key in ("added", "removed", "changed")):
        return "DRIFTED"
    return "LIVE"


def render_context(snapshot: Mapping[str, Any]) -> str:
    projected = project_topology_context(snapshot)
    lines = ["MWP TOPOLOGY READBACK (metadata-only; fail-closed):"]
    for key in ("user_id", "installation_id", "login_surface_id", "agent_id", "status", "observed_at", "expires_at", "freshness", "drift", "components", "world_model"):
        if key in projected:
            lines.append(f"- {key}: {projected[key]}")
    return "\n".join(lines)
