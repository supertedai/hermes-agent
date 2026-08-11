import json

from agent.mwp_change_ledger import record_change
from agent.mwp_receipt_adapters import graph_write_receipt, obsidian_write_receipt


def make_event():
    return record_change(action="adapter-test", intent="metadata receipt", principal="morten", installation_id="i", login_surface_id="s", agent_id="opus", system_scope="mwp")


def test_graph_without_runtime_authority_is_blocked(monkeypatch):
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    receipt = graph_write_receipt(make_event())
    assert receipt.status == "BLOCKED"
    assert "authority" in receipt.ref


def test_obsidian_without_vault_is_blocked(tmp_path):
    receipt = obsidian_write_receipt(make_event(), vault=tmp_path / "missing")
    assert receipt.status == "BLOCKED"


def test_obsidian_write_is_idempotent_and_readback_verified(tmp_path):
    receipt = obsidian_write_receipt(make_event(), vault=tmp_path)
    assert receipt.status == "VERIFIED"
    assert (tmp_path / ".mwp" / "receipts").is_dir()


def test_graph_fake_readback_verifies(monkeypatch):
    ev = make_event()
    monkeypatch.setenv("NEO4J_USER", "runtime-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "runtime-only")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps({"results": [{"data": [{"row": [ev.event_id]}]}]}).encode()

    receipt = graph_write_receipt(ev, opener=lambda request, timeout: Response())
    assert receipt.status == "VERIFIED"
