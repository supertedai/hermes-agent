import json

from agent.mwp_change_ledger import ChangeStatus, record_change
from agent.mwp_receipt_pipeline import reconcile_event


def test_pipeline_keeps_same_identity_and_open_without_external_authority(tmp_path):
    event = record_change(action="pipeline", intent="receipt pipeline", principal="morten", installation_id="i", login_surface_id="s", agent_id="opus", system_scope="mwp")
    result = reconcile_event(event, repo=".", ledger_path=tmp_path / "ledger.jsonl")
    assert result.event_id == event.event_id
    assert result.cad_id == event.cad_id
    assert result.status in {ChangeStatus.OPEN, ChangeStatus.BLOCKED}
    assert len(result.receipts) == 3
    assert (tmp_path / "ledger.jsonl").is_file()


def test_pipeline_can_complete_with_verified_adapters(tmp_path, monkeypatch):
    event = record_change(action="pipeline", intent="receipt pipeline", principal="morten", installation_id="i", login_surface_id="s", agent_id="opus", system_scope="mwp")
    monkeypatch.setenv("NEO4J_USER", "runtime-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "runtime-only")
    vault = tmp_path / "vault"; vault.mkdir()

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps({"results": [{"data": [{"row": [event.event_id]}]}]}).encode()

    result = reconcile_event(event, repo=".", ledger_path=tmp_path / "ledger.jsonl", graph_opener=lambda request, timeout: Response(), vault=vault)
    assert result.status is ChangeStatus.COMPLETE
    assert (tmp_path / "vault" / ".mwp" / "receipts").is_dir()
