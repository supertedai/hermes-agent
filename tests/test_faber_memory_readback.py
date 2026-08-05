from __future__ import annotations

import json

from agent import faber_memory_readback as mr
from agent.continuous_pipeline import CANONICAL_MEMORY_LAYER_IDS


def payload(states):
    return {
        "user": "morten",
        "principal_exists": True,
        "layers": [
            {"key": k, "state": s, "reader": f"user_memory_layers.measure -> {k}", "n": 5 if s == "measured" else 0}
            for k, s in states.items()
        ],
    }


ALL_MEASURED = {k: "measured" for k in CANONICAL_MEMORY_LAYER_IDS}


def test_every_canonical_layer_is_always_reported():
    rb = mr.build_readback("morten", payload=payload(ALL_MEASURED))

    assert len(rb.layers) == 20
    assert [l.layer_id for l in rb.layers] == list(CANONICAL_MEMORY_LAYER_IDS)


def test_selected_and_excluded_partition_the_registry_without_drop():
    rb = mr.build_readback("morten", payload=payload(ALL_MEASURED))

    selected = {l.layer_id for l in rb.layers if l.selected}
    excluded = {l.layer_id for l in rb.layers if not l.selected}

    assert selected | excluded == set(CANONICAL_MEMORY_LAYER_IDS)
    assert not (selected & excluded)


def test_a_full_layer_left_unread_is_budget_crowded_out_not_empty():
    """The distinction the whole module exists for."""
    rb = mr.build_readback("morten", payload=payload(ALL_MEASURED), budget_tokens=1800)

    unread = [l for l in rb.layers if not l.selected]

    assert unread, "a 1800-token budget cannot fit 20 layers"
    assert all(l.reason == "budget_crowded_out" for l in unread)
    assert all(l.substrate_state == "measured" for l in unread)
    # Usable is a substrate fact; read_this_turn is a scheduling fact.
    assert rb.usable == 20
    assert rb.read_this_turn == len(CANONICAL_MEMORY_LAYER_IDS) - len(unread)


def test_a_bigger_budget_reads_more_layers():
    small = mr.build_readback("morten", payload=payload(ALL_MEASURED), budget_tokens=1800)
    large = mr.build_readback("morten", payload=payload(ALL_MEASURED), budget_tokens=20 * 256)

    assert large.read_this_turn > small.read_this_turn
    assert large.read_this_turn == 20


def test_substrate_state_wins_over_scheduling():
    """A blind layer the scheduler picked still supplies nothing."""
    states = dict(ALL_MEASURED)
    states["episodisk"] = "blind"

    rb = mr.build_readback("morten", payload=payload(states))
    episodisk = next(l for l in rb.layers if l.layer_id == "episodisk")

    assert episodisk.substrate_state == "blind"
    assert episodisk.reason == "blind"
    assert rb.usable == 19


def test_blind_absent_and_no_principal_stay_distinct():
    states = dict(ALL_MEASURED)
    states["kausalt"] = "blind"
    states["utility"] = "absent"
    states["erfaring"] = "no_principal"

    rb = mr.build_readback("morten", payload=payload(states))
    by_id = {l.layer_id: l for l in rb.layers}

    assert by_id["kausalt"].reason == "blind"
    assert by_id["utility"].reason == "absent"
    assert by_id["erfaring"].reason == "no_principal"


def test_unreachable_api_never_reports_a_usable_layer():
    rb = mr.build_readback("faber", payload={}, api_error="URLError: timed out")

    assert rb.usable == 0
    assert all(l.substrate_state == "unreachable" for l in rb.layers)
    assert rb.api_error.startswith("URLError")


def test_layer_missing_from_authority_is_flagged_not_assumed_empty():
    states = dict(ALL_MEASURED)
    del states["salient"]

    rb = mr.build_readback("morten", payload=payload(states))
    salient = next(l for l in rb.layers if l.layer_id == "salient")

    assert salient.substrate_state == "unreported_by_authority"
    assert salient.reason == "unreported_by_authority"


def test_absent_principal_is_carried_through():
    rb = mr.build_readback("faber", payload={"principal_exists": False, "layers": []})

    assert rb.principal_exists is False
    assert rb.usable == 0


def test_record_appends_a_complete_readback(tmp_path, monkeypatch):
    log = tmp_path / "memory-readback.jsonl"
    monkeypatch.setattr(mr, "fetch_layer_state", lambda p, **kw: (payload(ALL_MEASURED), ""))

    rb = mr.record("morten", log=log)

    line = log.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["canonical_layers"] == 20
    assert len(record["layers"]) == 20
    assert record["usable_for_principal"] == rb.usable
    assert record["read_this_turn"] == rb.read_this_turn
    assert record["budget_tokens"] == mr.DEFAULT_BUDGET_TOKENS


def test_an_agent_principal_is_surface_mismatch_not_absence():
    """Asking the User surface about a FleetAgent is a category error.

    Reporting `no_principal` for it would dress that error up as a measurement:
    it reads as "we looked, the layers are empty" when what happened is "we asked
    a surface that cannot describe this kind of principal".
    """
    rb = mr.build_readback("faber", payload={}, principal_kind="fleet_agent")

    assert len(rb.layers) == 20
    assert all(l.substrate_state == "surface_mismatch" for l in rb.layers)
    assert all(l.reason == "surface_mismatch" for l in rb.layers)
    assert rb.usable == 0
    record = rb.to_dict()
    assert record["principal_kind"] == "fleet_agent"
    assert record["surface_describes_principal"] is False


def test_surface_mismatch_is_distinct_from_no_principal():
    agent = mr.build_readback("faber", payload={}, principal_kind="fleet_agent")
    missing_user = mr.build_readback(
        "ukjent", payload=payload({k: "no_principal" for k in CANONICAL_MEMORY_LAYER_IDS})
    )

    agent_states = {l.substrate_state for l in agent.layers}
    user_states = {l.substrate_state for l in missing_user.layers}

    assert agent_states == {"surface_mismatch"}
    assert user_states == {"no_principal"}
    assert agent_states != user_states


def test_a_user_principal_still_reports_measured_state():
    """The fix must not turn every principal into a mismatch."""
    rb = mr.build_readback("morten", payload=payload(ALL_MEASURED), principal_kind="user")

    assert rb.usable == 20
    assert rb.to_dict()["surface_describes_principal"] is True


def test_record_does_not_call_the_wrong_surface_for_an_agent(tmp_path, monkeypatch):
    """A mismatch must not cost a pointless multi-second API round trip."""
    called = []
    monkeypatch.setattr(mr, "fetch_layer_state", lambda p, **kw: called.append(p) or ({}, ""))

    rb = mr.record("faber", log=tmp_path / "r.jsonl", principal_kind="fleet_agent")

    assert called == [], "the User surface must not be queried for a FleetAgent"
    assert rb.usable == 0
