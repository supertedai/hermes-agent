import subprocess

from agent.mwp_topology_discovery import TopologyItem, discover_local, readback


def fake_runner(command, **kwargs):
    text = " ".join(command)
    outputs = {
        "docker": "svc-a\timage:a\tUp 2 minutes\n",
        "systemctl": "hermes.service\tloaded active running Hermes\n",
        "ss": "LISTEN 0 128 127.0.0.1:9119 0.0.0.0:*\n",
        "ps": "999 python tools/gnn_training_daemon.py\n",
    }
    for key, value in outputs.items():
        if key in text:
            return subprocess.CompletedProcess(command, 0, value, "")
    return subprocess.CompletedProcess(command, 1, "", "")


def test_discovery_is_metadata_only_and_deterministic():
    items = discover_local(fake_runner)
    keys = {(item.source, item.key) for item in items}
    assert ("docker", "svc-a") in keys
    assert ("systemd", "hermes.service") in keys
    assert ("process", "python") in keys
    assert all("Up 2 minutes" in item.detail or item.source != "docker" for item in items)


def test_discovery_excludes_scanner_process(monkeypatch):
    monkeypatch.setattr("agent.mwp_topology_discovery.os.getpid", lambda: 123)

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "123 python3 scripts/mwp_topology_tick.py\n999 python daemon.py\n", "") if command[0] == "ps" else subprocess.CompletedProcess(command, 0, "", "")

    items = discover_local(runner)
    assert ("process", "python3") not in {(item.source, item.key) for item in items}


def test_drift_detects_added_removed_changed():
    old = readback((TopologyItem("docker", "old", "LIVE", "v1"),))
    new = readback((TopologyItem("docker", "new", "LIVE", "v2"), TopologyItem("systemd", "svc", "LIVE", "running")), old)
    assert new.added == ("docker:new", "systemd:svc")
    assert new.removed == ("docker:old",)
    assert new.changed == ()


def test_changed_item_is_detected():
    old = readback((TopologyItem("docker", "svc", "LIVE", "v1"),))
    new = readback((TopologyItem("docker", "svc", "LIVE", "v2"),), old)
    assert new.changed == ("docker:svc",)
