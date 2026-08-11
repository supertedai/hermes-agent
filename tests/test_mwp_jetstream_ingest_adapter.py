from agent.mwp_ingest_contract import IngestVerdict
from agent.mwp_jetstream_ingest_adapter import jetstream_to_ingest, validate_jetstream_ingest
from agent.mwp_jetstream_worldmodel_router import JetstreamSignal


def signal(**overrides):
    values = {
        "signal_id": "js-1", "source_id": "jetstream:source", "domain": "energy",
        "topic": "price anomaly", "entropy": 0.8, "freshness": "FRESH",
        "provenance_ref": "prov:1", "payload_ref": "payload:1",
        "gap_refs": ("gap:energy",), "evidence_refs": ("ev:1",), "injection_checked": True,
    }
    values.update(overrides)
    return JetstreamSignal(**values)


def base_envelope():
    return jetstream_to_ingest(signal(), principal_id="p1", tenant_id="t1", session_id="s1", conversation_id="c1", correlation_id="corr-1", observed_at="2026-08-09T12:00:00Z")


def test_jetstream_enters_as_hermes_system_ingest():
    envelope = base_envelope()
    assert envelope["runtime_path"] == "hermes-agent-engine"
    assert envelope["plane"] == "system"
    assert envelope["cortex_ref"] == "Cortex/world_model_hub"
    assert "payload" not in envelope
    verdict, blockers = validate_jetstream_ingest(envelope)
    assert verdict == IngestVerdict.VALID
    assert blockers == ()


def test_unchecked_jetstream_is_quarantined():
    envelope = jetstream_to_ingest(
        signal(injection_checked=False),
        principal_id="p1",
        tenant_id="t1",
        session_id="s1",
        conversation_id="c1",
        correlation_id="corr-1",
        observed_at="2026-08-09T12:00:00Z",
    )
    verdict, blockers = validate_jetstream_ingest(envelope)
    assert verdict == "QUARANTINED"
    assert blockers == ("injection scan not verified",)


def test_jetstream_idempotency_is_stable():
    a = base_envelope()
    b = base_envelope()
    assert a["idempotency_key"] == b["idempotency_key"] == "jetstream:js-1"
