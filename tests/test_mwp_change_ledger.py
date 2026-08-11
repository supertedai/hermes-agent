import json

import pytest

from agent.mwp_change_ledger import (
    ChangeStatus,
    DestinationReceipt,
    append_event,
    record_change,
    validate_event_metadata,
)


def receipt(destination):
    return DestinationReceipt(destination, "VERIFIED", f"{destination}-ref", "2026-08-06T00:00:00Z")


def test_every_change_gets_provisional_cad_adr_bl_and_stays_open_without_receipts(tmp_path):
    event = record_change(
        action="topology discovery",
        intent="map service placement",
        principal="morten",
        installation_id="install-a",
        login_surface_id="desktop-a",
        agent_id="opus",
        system_scope="symbiose",
        evidence_refs=("runtime:probe-1",),
    )
    assert event.cad_id.startswith("CAD-EVT-")
    assert event.adr_id.startswith("ADR-EVT-")
    assert event.bl_id.startswith("BL-EVT-")
    assert event.status is ChangeStatus.OPEN
    assert "git" in event.gap and "graph" in event.gap and "obsidian" in event.gap
    append_event(event, tmp_path / "ledger.jsonl")
    lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_id"] == event.event_id


def test_complete_requires_all_three_destination_receipts():
    event = record_change(
        action="verified alignment",
        intent="close ASI registry row",
        principal="morten",
        installation_id="install-a",
        login_surface_id="tui-a",
        agent_id="opus",
        system_scope="symbiose",
        receipts=(receipt("git"), receipt("graph"), receipt("obsidian")),
    )
    assert event.status is ChangeStatus.COMPLETE
    validate_event_metadata(event)


def test_missing_identity_is_rejected():
    with pytest.raises(ValueError, match="agent_id"):
        record_change(
            action="x", intent="y", principal="morten", installation_id="i",
            login_surface_id="s", agent_id="", system_scope="system",
        )


def test_registry_is_metadata_only():
    event = record_change(
        action="x", intent="y", principal="morten", installation_id="i",
        login_surface_id="s", agent_id="opus", system_scope="system",
    )
    assert "payload" not in json.dumps(event.as_dict())
