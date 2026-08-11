import json

import pytest

from agent.mwp_asi_alignment_registry import (
    ASIStatus,
    ASIAlignmentRow,
    build_status_quo,
    refresh_from_topology,
)


def test_status_quo_is_open_and_conservative():
    registry = build_status_quo()
    assert registry.registry_id == "mwp-asi-status-quo-v1"
    assert registry.status == "OPEN"
    assert registry.open_rows == 9
    assert any(row.status is ASIStatus.LIVE_VERIFIED for row in registry.rows) is False
    assert any(row.status is ASIStatus.BLOCKED for row in registry.rows)
    assert any(row.status is ASIStatus.UNKNOWN for row in registry.rows)


def test_refresh_promotes_only_fresh_no_drift_topology_to_connected_read_only():
    refreshed = refresh_from_topology(build_status_quo(), {"freshness": {"status": "FRESH"}, "drift": {}})
    row = next(row for row in refreshed.rows if row.key == "per-user-topology")
    assert row.status is ASIStatus.CONNECTED_READ_ONLY
    assert next(row for row in refreshed.rows if row.key == "world-model-hub-alignment").status is ASIStatus.UNVERIFIED


def test_refresh_marks_topology_drift_without_promoting_world_model():
    refreshed = refresh_from_topology(build_status_quo(), {"freshness": {"status": "FRESH"}, "drift": {"added": ["service:x"]}})
    row = next(row for row in refreshed.rows if row.key == "per-user-topology")
    assert row.status is ASIStatus.DRIFTED


def test_duplicate_alignment_keys_are_rejected():
    row = ASIAlignmentRow(
        key="same",
        asi_capability="capability",
        intent_refs="ADR",
        implementation="implementation",
        git_source="git",
        daemon_or_sync="daemon",
        service_route="route",
        scope="scope",
        evidence="metadata evidence",
        freshness="freshness",
        drift="drift",
        rollback_gate="rollback",
        status=ASIStatus.UNKNOWN,
        gap="gap",
    )
    with pytest.raises(ValueError, match="duplicate"):
        from agent.mwp_asi_alignment_registry import ASIAlignmentReadback
        ASIAlignmentReadback("x", "y", (row, row))


def test_status_quo_is_metadata_only():
    payload = build_status_quo().as_dict()
    text = json.dumps(payload)
    assert "raw_output" not in text
    assert "secret" not in text
    assert "token" not in text
    assert all("gap" in row for row in payload["rows"])
