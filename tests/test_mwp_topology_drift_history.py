from agent.mwp_flyby_queue import SurfaceIdentity
from agent.mwp_topology_discovery import TopologyItem, readback
from agent.mwp_topology_drift_history import append_drift, read_drift, record_from_readback


def test_scoped_drift_history_preserves_last_seen_hash_and_drift(tmp_path):
    identity = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    rb = readback((TopologyItem("service", "opus", "LIVE", "v1"),))
    record = record_from_readback(identity, rb)
    append_drift(tmp_path, record)
    rows = read_drift(tmp_path, identity)
    assert len(rows) == 1
    assert rows[0].last_seen == rb.recorded_at
    assert rows[0].inventory_hash == rb.inventory_hash
    assert rows[0].version_config_hash == rb.inventory_hash


def test_drift_history_does_not_cross_scope(tmp_path):
    a = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    b = SurfaceIdentity("install-b", "desktop-b", "morten", "opus")
    record = record_from_readback(a, readback(()))
    append_drift(tmp_path, record)
    assert read_drift(tmp_path, a)
    assert read_drift(tmp_path, b) == ()
