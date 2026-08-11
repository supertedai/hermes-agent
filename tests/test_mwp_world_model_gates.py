from agent.mwp_world_model_gates import WorldModelVerdict, metadata_readback, validate_retrieval_quality, validate_rollback_handles


def targets():
    return {
        "graph": {"service_reachable": True, "snapshot_handle": "g-snap", "rollback_ref": "g-rb"},
        "qdrant": {"service_reachable": True, "snapshot_handle": "q-snap", "rollback_ref": "q-rb"},
        "gnn": {"service_reachable": True, "checkpoint_handle": "n-ckpt", "rollback_ref": "n-rb"},
    }


def quality():
    return {"stable_chunk_identity": True, "owner_labels": True, "precision_at_k": 0.8, "recall_at_k": 0.7, "gnn_degraded": False}


def test_rollback_complete_only_with_all_handles():
    verdict, blockers = validate_rollback_handles(targets())
    assert verdict == WorldModelVerdict.COMPLETE
    assert blockers == ()


def test_missing_rollback_handle_blocks():
    payload = targets()
    payload["qdrant"]["rollback_ref"] = ""
    verdict, blockers = validate_rollback_handles(payload)
    assert verdict == WorldModelVerdict.BLOCKED
    assert "qdrant rollback_ref missing" in blockers


def test_quality_requires_labels_identity_metrics_and_healthy_gnn():
    verdict, blockers = validate_retrieval_quality(quality())
    assert verdict == WorldModelVerdict.COMPLETE
    payload = quality()
    payload["stable_chunk_identity"] = False
    payload["gnn_degraded"] = True
    verdict, blockers = validate_retrieval_quality(payload)
    assert verdict == WorldModelVerdict.PARTIAL
    assert "stable chunk identity missing" in blockers
    assert "GNN degraded" in blockers


def test_current_discovery_is_blocked_but_metadata_only():
    verdict = metadata_readback(
        {"graph": {"service_reachable": True}, "qdrant": {"service_reachable": True}, "gnn": {"service_reachable": True}},
        {"stable_chunk_identity": False, "owner_labels": False, "gnn_degraded": True},
    )
    assert verdict["rollback_verdict"] == WorldModelVerdict.BLOCKED
    assert verdict["quality_verdict"] == WorldModelVerdict.PARTIAL
    assert verdict["raw_payload_included"] is False
