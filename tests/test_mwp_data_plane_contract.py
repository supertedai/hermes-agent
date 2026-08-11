from agent.mwp_data_plane_contract import (
    DataPlaneVerdict,
    metadata_readback,
    validate_data_plane_readback,
    validate_gnn_model_descriptor,
    validate_vector_collection_descriptor,
)


def valid():
    return {
        "schema_id": "memory-event",
        "schema_version": "1",
        "canonical_authority_ref": "mwp-authority",
        "scope": "user:p1",
        "provenance_ref": "prov-1",
        "projection_state": "FRESH",
        "derived_only": True,
        "read_after_write": True,
        "rollback_ref": "rb-1",
        "quality_baseline": True,
    }


def vector_descriptor():
    return {
        "collection_id": "canonical_facts",
        "schema_id": "fact-v1",
        "schema_version": "1",
        "owner": "memory-fabric",
        "embedding_model_ref": "model@hash",
        "dimension": 1536,
        "distance_metric": "cosine",
        "point_identity": "canonical_entity_id",
        "scope_policy": "tenant-principal",
        "payload_indexes": ["tenant_id", "principal_id", "scope"],
        "derived_only": True,
    }


def gnn_descriptor():
    return {
        "model_id": "relation-ranker",
        "model_version": "1",
        "checkpoint_hash": "sha256:abc",
        "feature_schema": "features-v1",
        "label_schema": "edges-v1",
        "evaluation_baseline": "baseline-1",
        "serving_route": "cortex/rank",
        "rollback_ref": "checkpoint:prev",
        "derived_only": True,
        "leakage_controls": True,
    }


def test_vector_collection_descriptor_requires_governance_fields():
    assert validate_vector_collection_descriptor(vector_descriptor()) == (DataPlaneVerdict.COMPLETE, ())
    verdict, blockers = validate_vector_collection_descriptor(vector_descriptor() | {"dimension": 0})
    assert verdict == DataPlaneVerdict.BLOCKED
    assert blockers == ("invalid vector:dimension",)


def test_gnn_descriptor_requires_checkpoint_and_leakage_controls():
    assert validate_gnn_model_descriptor(gnn_descriptor()) == (DataPlaneVerdict.COMPLETE, ())
    verdict, blockers = validate_gnn_model_descriptor(gnn_descriptor() | {"leakage_controls": False})
    assert verdict == DataPlaneVerdict.OPEN
    assert blockers == ("gnn leakage controls missing",)


def test_complete_data_plane_readback():
    assert validate_data_plane_readback(valid()) == (DataPlaneVerdict.COMPLETE, ())


def test_derived_store_without_scope_or_rollback_blocks():
    payload = valid() | {"scope": "", "rollback_ref": ""}
    verdict, blockers = validate_data_plane_readback(payload)
    assert verdict == DataPlaneVerdict.BLOCKED
    assert "missing scope" in blockers
    assert "rollback_ref missing" in blockers


def test_projection_not_marked_derived_blocks():
    payload = valid() | {"derived_only": False}
    verdict, blockers = validate_data_plane_readback(payload)
    assert verdict == DataPlaneVerdict.BLOCKED
    assert "derived store is not labelled derived_only" in blockers


def test_without_quality_baseline_remains_open():
    payload = valid() | {"quality_baseline": False}
    verdict, blockers = validate_data_plane_readback(payload)
    assert verdict == DataPlaneVerdict.OPEN
    assert blockers == ("quality baseline missing",)


def test_metadata_only_readback():
    result = metadata_readback(valid())
    assert result["verdict"] == DataPlaneVerdict.COMPLETE
    assert result["raw_payload_included"] is False
