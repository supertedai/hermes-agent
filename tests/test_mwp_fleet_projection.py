from datetime import datetime, timezone, timedelta

import pytest

from agent.mwp_fleet_projection import (
    AgentRecord,
    ProjectionStatus,
    metadata_readback,
    project_agents,
    records_from_registry_payload,
    select_candidates,
)


NOW = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)


def test_projection_keeps_declared_stale_unknown_and_live_separate():
    rows = project_agents(
        [
            AgentRecord("live", last_active="2026-08-06T12:55:00Z", capabilities=("testing",)),
            AgentRecord("stale", last_active="2026-08-06T10:00:00Z", capabilities=("testing",)),
            AgentRecord("unknown", capabilities=("testing",)),
            AgentRecord("declared", last_active="2026-08-06T12:55:00Z", capabilities=("testing",), superseded="old"),
            AgentRecord("unmeasured", last_active="2026-08-06T12:55:00Z"),
        ],
        now=NOW,
        freshness_seconds=900,
    )
    statuses = {row.agent_id: row.status for row in rows}
    assert statuses == {
        "declared": ProjectionStatus.DECLARED_ONLY,
        "live": ProjectionStatus.LIVE_VERIFIED,
        "stale": ProjectionStatus.STALE,
        "unknown": ProjectionStatus.UNKNOWN,
        "unmeasured": ProjectionStatus.NO_CAPABILITY_EVIDENCE,
    }


def test_select_candidates_is_capability_and_freshness_gated():
    rows = project_agents(
        [
            AgentRecord("live", last_active="2026-08-06T12:55:00Z", capabilities=("testing", "review")),
            AgentRecord("other", last_active="2026-08-06T12:55:00Z", capabilities=("infra",)),
            AgentRecord("stale", last_active="2026-08-06T10:00:00Z", capabilities=("testing",)),
        ],
        now=NOW,
        freshness_seconds=900,
    )
    assert [row.agent_id for row in select_candidates(rows, capability="testing")] == ["live"]
    assert select_candidates(rows, capability="missing") == ()


def test_metadata_readback_is_aggregate_only():
    rows = project_agents(
        [AgentRecord("a", last_active="2026-08-06T12:55:00Z", capabilities=("x",))],
        now=NOW,
    )
    readback = metadata_readback(rows)
    assert readback["candidate_count"] == 1
    assert readback["raw_payload_included"] is False
    assert "x" not in str(readback)


def test_invalid_freshness_and_empty_capability_fail_closed():
    with pytest.raises(ValueError, match="freshness_seconds"):
        project_agents([], now=NOW, freshness_seconds=-1)
    with pytest.raises(ValueError, match="capability is required"):
        select_candidates((), capability=" ")


def test_registry_payload_adapter_is_metadata_only_and_dynamic():
    records = records_from_registry_payload({
        "agents": [
            {"id": "testing", "kind": "core-role", "last_active": "2026-08-06T12:55:00Z",
             "skills": [{"domain": "test-authoring"}]},
            {"id": "empty", "skills": []},
            {"kind": "missing-id"},
        ]
    })
    assert [item.agent_id for item in records] == ["testing", "empty"]
    assert records[0].capabilities == ("test-authoring",)
