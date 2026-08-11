from agent.mwp_cross_surface_truth import (
    TruthVerdict,
    validate_mutation_envelope,
    validate_strict_mutation_envelope,
    validate_strict_truth_receipts,
    validate_truth_receipts,
)


def envelope():
    return {"mutation_id":"m1","idempotency_key":"i1","operation":"update","canonical_key":"tenant/personal/note/n1","principal_id":"u1","auth_context_ref":"a1","canonical_authority_ref":"canon1","source_surface":"desktop","expected_version":2,"provenance_ref":"p1","occurred_at":"2026-08-06T00:00:00Z"}


def canonical():
    return {"canonical_key":"tenant/personal/note/n1","entity_version":3,"content_hash":"h3"}


def test_envelope_requires_expected_version_for_update():
    e=envelope(); e.pop("expected_version")
    assert validate_mutation_envelope(e)[0] == TruthVerdict.CONFLICT


def test_strict_envelope_requires_full_topology_scope():
    verdict, blockers = validate_strict_mutation_envelope(envelope())
    assert verdict == TruthVerdict.BLOCKED
    assert "missing:tenant_id" in blockers
    assert "missing:installation_id" in blockers
    assert "missing:device_id" in blockers
    assert "missing:login_surface_id" in blockers
    assert "missing:session_id" in blockers
    assert "missing:system_scope" in blockers


def test_strict_envelope_accepts_full_topology_scope():
    payload = envelope() | {
        "tenant_id": "t1",
        "installation_id": "i1",
        "device_id": "d1",
        "login_surface_id": "ai.byopus.com",
        "session_id": "s1",
        "system_scope": "personal",
    }
    assert validate_strict_mutation_envelope(payload) == (TruthVerdict.COMPLETE, ())


def strict_envelope():
    return envelope() | {
        "tenant_id": "t1",
        "installation_id": "i1",
        "device_id": "d1",
        "login_surface_id": "ai.byopus.com",
        "session_id": "s1",
        "system_scope": "personal",
    }


def strict_canonical():
    return canonical() | {
        "canonical_authority_ref": "canon1",
        "provenance_ref": "p1",
        "readback_at": "2026-08-09T00:00:00Z",
        "rollback_ref": "rb1",
        "freshness_seconds": 30,
    }


def strict_outbox():
    return {
        "mutation_id": "m1",
        "canonical_version": 3,
        "content_hash": "h3",
        "provenance_ref": "p1",
        "delivery_state": "DELIVERED",
        "replay_idempotency": "i1",
    }


def test_strict_truth_receipt_requires_authority_provenance_freshness_and_rollback():
    verdict, blockers = validate_strict_truth_receipts(strict_envelope(), canonical(), strict_outbox(), [])
    assert verdict == TruthVerdict.PENDING_READBACK
    assert "canonical:missing:canonical_authority_ref" in blockers

    verdict, blockers = validate_strict_truth_receipts(strict_envelope(), strict_canonical(), {"mutation_id": "m1"}, [])
    assert verdict == TruthVerdict.BLOCKED
    assert "outbox:missing:canonical_version" in blockers


def test_strict_truth_receipt_accepts_complete_metadata():
    projection = {"surface_id": "web", "projection_state": "FRESH", "entity_version": 3, "content_hash": "h3"}
    assert validate_strict_truth_receipts(strict_envelope(), strict_canonical(), strict_outbox(), [projection], required_surfaces=["web"]) == (TruthVerdict.COMPLETE, ())


def test_strict_truth_receipt_rejects_authority_mismatch():
    canonical_readback = strict_canonical() | {"canonical_authority_ref": "other"}
    verdict, blockers = validate_strict_truth_receipts(strict_envelope(), canonical_readback, strict_outbox(), [])
    assert verdict == TruthVerdict.BLOCKED
    assert blockers == ("canonical:authority_mismatch",)


def test_strict_truth_receipt_rejects_outbox_hash_mismatch():
    outbox = strict_outbox() | {"content_hash": "wrong"}
    verdict, blockers = validate_strict_truth_receipts(strict_envelope(), strict_canonical(), outbox, [])
    assert verdict == TruthVerdict.DIVERGED
    assert blockers == ("outbox:hash_mismatch",)


def test_truth_requires_canonical_and_outbox():
    assert validate_truth_receipts(envelope(), None, None, [])[0] == TruthVerdict.PENDING_READBACK
    assert validate_truth_receipts(envelope(), canonical(), None, [])[0] == TruthVerdict.BLOCKED


def test_truth_requires_fresh_matching_projection():
    out={"mutation_id":"m1","canonical_version":3}
    stale={"surface_id":"chat","projection_state":"STALE","entity_version":2,"content_hash":"h2"}
    assert validate_truth_receipts(envelope(), canonical(), out, [stale], required_surfaces=["chat"])[0] == TruthVerdict.STALE
    fresh={"surface_id":"chat","projection_state":"FRESH","entity_version":3,"content_hash":"h3"}
    assert validate_truth_receipts(envelope(), canonical(), out, [fresh], required_surfaces=["chat"])[0] == TruthVerdict.COMPLETE


def test_hash_divergence_fails_closed():
    out={"mutation_id":"m1","canonical_version":3}
    bad={"surface_id":"desktop","projection_state":"FRESH","entity_version":3,"content_hash":"wrong"}
    assert validate_truth_receipts(envelope(), canonical(), out, [bad], required_surfaces=["desktop"])[0] == TruthVerdict.DIVERGED
