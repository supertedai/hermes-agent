from agent.mwp_change_ledger import record_change
from agent.mwp_receipt_coordinator import git_receipt, obsidian_probe, receipts_for_event


def make_event():
    return record_change(
        action="receipt probe", intent="verify destinations", principal="morten",
        installation_id="install-a", login_surface_id="desktop-a",
        agent_id="opus", system_scope="mwp",
    )


def test_git_receipt_is_readback_only():
    receipt = git_receipt(".")
    assert receipt.destination == "git"
    assert receipt.status == "VERIFIED"
    assert "head=" in receipt.ref


def test_unconfigured_obsidian_never_claims_write():
    receipt = obsidian_probe("")
    assert receipt.destination == "obsidian"
    assert receipt.status != "VERIFIED"
    assert receipt.ref == "vault path not configured"


def test_coordinator_keeps_external_receipts_conservative():
    receipts = receipts_for_event(make_event(), repo=".")
    statuses = {r.destination: r.status for r in receipts}
    assert statuses["git"] == "VERIFIED"
    assert statuses["graph"] != "VERIFIED"
    assert statuses["obsidian"] != "VERIFIED"
