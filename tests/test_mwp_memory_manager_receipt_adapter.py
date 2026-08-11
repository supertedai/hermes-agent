import pytest

from agent.mwp_ingest_contract import IngestVerdict, validate_ingest_envelope
from agent.mwp_memory_manager_receipt_adapter import memory_lifecycle_envelope


def receipt(event_type='prefetch'):
    return memory_lifecycle_envelope(
        event_type=event_type,
        provider_name='builtin',
        principal_id='u1',
        tenant_id='t1',
        system_scope='personal',
        session_id='s1',
        conversation_id='c1',
        correlation_id='corr1',
        observed_at='2026-08-09T00:00:00Z',
    )


def test_lifecycle_receipt_is_valid_ingest_metadata():
    envelope = receipt()
    assert validate_ingest_envelope(envelope) == (IngestVerdict.VALID, ())
    assert envelope['payload_included'] is False
    assert 'content' not in envelope


def test_lifecycle_events_map_to_expected_operations():
    assert receipt('prefetch')['operation'] == 'observe'
    assert receipt('queue_prefetch')['operation'] == 'observe'
    assert receipt('sync_turn')['operation'] == 'outcome'


def test_lifecycle_receipt_is_deterministically_idempotent():
    assert receipt() == receipt()


def test_lifecycle_receipt_rejects_missing_scope():
    with pytest.raises(ValueError):
        memory_lifecycle_envelope(
            event_type='prefetch', provider_name='builtin', principal_id='u1', tenant_id='',
            system_scope='personal', session_id='s1', conversation_id='c1',
            correlation_id='corr1', observed_at='2026-08-09T00:00:00Z',
        )
