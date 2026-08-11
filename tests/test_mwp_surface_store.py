import json

import pytest

from agent.mwp_flyby_queue import SurfaceIdentity
from agent.mwp_surface_store import read_scoped_snapshot, write_scoped_snapshot


def test_same_user_different_installations_are_isolated(tmp_path):
    a = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    b = SurfaceIdentity("install-b", "desktop-b", "morten", "opus")
    write_scoped_snapshot(tmp_path, a, {"status": "LIVE", "marker": "A"})
    write_scoped_snapshot(tmp_path, b, {"status": "BLOCKED", "marker": "B"})
    read_a = read_scoped_snapshot(tmp_path, a)
    read_b = read_scoped_snapshot(tmp_path, b)
    assert read_a is not None and read_a["marker"] == "A"
    assert read_b is not None and read_b["marker"] == "B"


def test_same_install_different_surfaces_are_isolated(tmp_path):
    a = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    b = SurfaceIdentity("install-a", "tui-a", "morten", "opus")
    write_scoped_snapshot(tmp_path, a, {"marker": "desktop"})
    write_scoped_snapshot(tmp_path, b, {"marker": "tui"})
    read_a = read_scoped_snapshot(tmp_path, a)
    read_b = read_scoped_snapshot(tmp_path, b)
    assert read_a is not None and read_a["marker"] == "desktop"
    assert read_b is not None and read_b["marker"] == "tui"


def test_scope_tampering_fails_closed(tmp_path):
    identity = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    path = write_scoped_snapshot(tmp_path, identity, {"marker": "safe"})
    data = json.loads(path.read_text())
    data["installation_id"] = "install-b"
    path.write_text(json.dumps(data))
    assert read_scoped_snapshot(tmp_path, identity) is None


def test_private_payload_is_rejected(tmp_path):
    identity = SurfaceIdentity("install-a", "desktop-a", "morten", "opus")
    with pytest.raises(ValueError):
        write_scoped_snapshot(tmp_path, identity, {"raw_payload": "no"})
