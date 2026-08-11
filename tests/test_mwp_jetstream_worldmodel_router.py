from agent.mwp_jetstream_worldmodel_router import (
    JetstreamSignal,
    ProjectionStatus,
    route_signal,
)


def signal(**overrides):
    values = {
        "signal_id": "js-1",
        "source_id": "jetstream:source",
        "domain": "energy",
        "topic": "price anomaly",
        "entropy": 0.8,
        "freshness": "FRESH",
        "provenance_ref": "prov:1",
        "payload_ref": "payload:1",
        "gap_refs": ("gap:energy",),
        "evidence_refs": ("ev:1",),
        "injection_checked": True,
    }
    values.update(overrides)
    return JetstreamSignal(**values)


def test_high_entropy_gap_routes_cortex_and_scoped_domains():
    decision = route_signal(signal(), domain_agents=("Helios", "energy-steward"))
    assert decision.status is ProjectionStatus.ROUTE_TO_CORTEX_AND_DOMAINS
    assert decision.cortex_target == "Cortex/world_model_hub"
    assert decision.domain_targets == ("Helios", "energy-steward")
    assert decision.metadata_only


def test_low_entropy_without_gap_routes_cortex_only():
    decision = route_signal(signal(entropy=0.2, gap_refs=()))
    assert decision.status is ProjectionStatus.ROUTE_TO_CORTEX_ONLY
    assert decision.domain_targets == ()


def test_missing_injection_check_quarantines():
    decision = route_signal(signal(injection_checked=False))
    assert decision.status is ProjectionStatus.QUARANTINE
    assert "injection scan not verified" in decision.blockers


def test_stale_signal_is_dropped_before_fanout():
    decision = route_signal(signal(freshness="STALE"))
    assert decision.status is ProjectionStatus.DROP_STALE
    assert decision.domain_targets == ()


def test_entropy_range_and_required_provenance_are_validated():
    try:
        signal(entropy=1.1)
    except ValueError as exc:
        assert "entropy" in str(exc)
    else:
        raise AssertionError("out-of-range entropy must fail closed")

    try:
        signal(provenance_ref="")
    except ValueError as exc:
        assert "missing Jetstream signal fields" in str(exc)
    else:
        raise AssertionError("missing provenance must fail closed")
