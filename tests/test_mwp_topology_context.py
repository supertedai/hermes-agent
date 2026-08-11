from datetime import datetime, timezone, timedelta
import json

from agent.mwp_topology_context import classify_topology_status, load_topology_context, project_topology_context, render_context


def test_projection_preserves_scope_and_removes_private_fields():
    result = project_topology_context({
        "user_id": "morten", "installation_id": "i-a", "login_surface_id": "desktop-a",
        "status": "DEGRADED", "observed_at": "now", "raw_payload": "private",
        "components": [{"name": "neo4j", "status": "LIVE", "version": "x"}],
    })
    assert result["user_id"] == "morten"
    assert result["status"] == "DEGRADED"
    assert "raw_payload" not in result


def test_render_is_metadata_only():
    text = render_context({"user_id": "morten", "status": "BLOCKED", "freshness": {"status": "STALE"}})
    assert "MWP TOPOLOGY READBACK" in text
    assert "morten" in text
    assert "STALE" in text
    assert "payload" not in text.lower()


def test_load_injects_freshness_and_scope(tmp_path):
    path = tmp_path / "readback.json"
    observed = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    path.write_text(json.dumps({"recorded_at": observed.isoformat().replace("+00:00", "Z"), "inventory_hash": "h", "drift": {"added": ["x"]}}))
    result = load_topology_context(path, now=observed + timedelta(seconds=10), ttl_seconds=60, scope={"user_id": "morten", "installation_id": "i-a", "login_surface_id": "desktop-a"})
    assert result["status"] == "LIVE"
    assert result["freshness"]["status"] == "FRESH"
    assert result["user_id"] == "morten"
    assert result["drift"] == {"added": ["x"]}


def test_load_fails_closed_when_stale_or_missing(tmp_path):
    missing = load_topology_context(tmp_path / "missing.json")
    assert missing["status"] == "UNKNOWN"
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"recorded_at": "2026-08-06T12:00:00Z", "drift": {}}))
    stale = load_topology_context(path, now=datetime(2026, 8, 6, 12, 20, tzinfo=timezone.utc), ttl_seconds=60)
    assert stale["status"] == "STALE"
    assert stale["freshness"]["status"] == "STALE"


def test_dynamic_status_is_fail_closed():
    assert classify_topology_status({"status": "UNKNOWN"}) == "UNKNOWN"
    assert classify_topology_status({"status": "STALE"}) == "STALE"
    assert classify_topology_status({"status": "LIVE", "freshness": {"status": "FRESH"}, "drift": {"added": ["service:x"]}}) == "DRIFTED"
    assert classify_topology_status({"status": "LIVE", "freshness": {"status": "FRESH"}, "drift": {}}) == "LIVE"
