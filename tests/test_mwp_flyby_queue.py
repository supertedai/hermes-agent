from agent.mwp_flyby_queue import SurfaceIdentity, digest_flyby, drain_at_safe_point, enqueue, route_flyby, surface_snapshot_path


def test_surface_identity_isolation():
    a = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    b = SurfaceIdentity("install-b", "desktop-b", "morten", "opus")
    assert surface_snapshot_path("/tmp/topology", a) != surface_snapshot_path("/tmp/topology", b)


def test_flyby_queue_and_safe_insertion(tmp_path):
    path = tmp_path / "flyby.jsonl"
    d = digest_flyby(classification="relevant", claim="topology drift", evidence=("snapshot-ref",), impact_on_primary="low", recommended_action="inspect next tick", confidence="medium", target_scope="mwp")
    enqueue(d, path)
    drained = drain_at_safe_point(path, safe_point="between-tasks")
    assert len(drained) == 1
    assert drained[0].flyby_id == d.flyby_id
    assert drained[0].queued is False
    assert "between-tasks" in drained[0].recommended_action


def test_worker_digest_queue_safe_point_e2e(tmp_path):
    seen = []

    def worker(metadata):
        seen.append(metadata)
        return {
            "classification": "relevant",
            "claim": "service drift",
            "evidence": ["topology-ref-1"],
            "impact_on_primary": "low",
            "recommended_action": "review next safe point",
            "confidence": "medium",
            "target_scope": "install-a/desktop-a/morten/opus",
        }

    path = tmp_path / "queue.jsonl"
    digest = route_flyby({"id": "flyby-source-1", "source": "session-ref", "scope": "mwp", "claim": "candidate"}, bounded_worker=worker, queue_path=path)
    assert seen == [{"id": "flyby-source-1", "source": "session-ref", "scope": "mwp", "claim": "candidate"}]
    drained = drain_at_safe_point(path, safe_point="after-current-task")
    assert len(drained) == 1
    assert drained[0].flyby_id == digest.flyby_id
    assert drained[0].classification == "relevant"
    assert drained[0].queued is False
    assert "after-current-task" in drained[0].recommended_action


def test_worker_private_result_is_rejected(tmp_path):
    def worker(_metadata):
        return {"raw_payload": "private"}

    try:
        route_flyby({"id": "x", "scope": "mwp"}, bounded_worker=worker, queue_path=tmp_path / "q")
    except ValueError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("private worker result was accepted")
