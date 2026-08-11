import time

import pytest

from agent.mwp_lateral_bus import append_message, make_message, read_messages


def msg(**kwargs):
    return make_message(
        message_id=kwargs.get("message_id", "m-1"), source_agent_id="opus", target_agent_id="helios",
        user_id="morten", installation_id="install-a", login_surface_id="desktop-a",
        source_ref="world-ref-1", classification="metadata", metadata={"status": "LIVE"},
        recorded_at=kwargs.get("recorded_at", 1000), freshness_ttl=kwargs.get("freshness_ttl", 100),
    )


def test_lateral_bus_preserves_scope_provenance_and_freshness(tmp_path):
    path = tmp_path / "bus.jsonl"
    append_message(path, msg())
    rows = read_messages(path, target_agent_id="helios", user_id="morten", installation_id="install-a", login_surface_id="desktop-a", now=1050)
    assert len(rows) == 1
    assert rows[0].source_ref == "world-ref-1"
    assert rows[0].status(now=1050) == "FRESH"


def test_stale_and_wrong_scope_are_not_delivered(tmp_path):
    path = tmp_path / "bus.jsonl"
    append_message(path, msg(recorded_at=1000, freshness_ttl=10))
    assert read_messages(path, target_agent_id="helios", user_id="morten", installation_id="install-a", login_surface_id="desktop-a", now=1020) == ()
    assert read_messages(path, target_agent_id="helios", user_id="morten", installation_id="install-b", login_surface_id="desktop-b", now=1001) == ()


def test_private_metadata_rejected():
    with pytest.raises(ValueError):
        make_message(message_id="x", source_agent_id="a", target_agent_id="b", user_id="u", installation_id="i", login_surface_id="s", source_ref="r", classification="x", metadata={"raw_payload": "no"})
