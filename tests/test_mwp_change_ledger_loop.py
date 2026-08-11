import json

from agent.mwp_change_ledger import ChangeStatus, DestinationReceipt, record_change, update_receipts
from agent.mwp_change_ledger_loop import tick_for_change_event


def make_event():
    return record_change(
        action="test", intent="test loop", principal="morten",
        installation_id="install-a", login_surface_id="desktop-a",
        agent_id="opus", system_scope="mwp",
    )


def verified():
    return tuple(DestinationReceipt(name, "VERIFIED", f"{name}-ref", "now") for name in ("git", "graph", "obsidian"))


def test_open_ledger_event_is_non_stopping():
    tick = tick_for_change_event(make_event(), next_action="continue topology lane")
    assert tick.continue_loop is True
    assert tick.blocker.startswith("missing receipts")
    assert tick.readback["ledger_status"] == "OPEN"


def test_complete_event_does_not_claim_parent_completion():
    tick = tick_for_change_event(update_receipts(make_event(), verified()))
    assert tick.complete is False
    assert tick.continue_loop is False
    assert tick.next_action == "continue parent coverage"


def test_receipts_reconcile_without_changing_event_identity():
    original = make_event()
    reconciled = update_receipts(original, verified())
    assert reconciled.event_id == original.event_id
    assert reconciled.cad_id == original.cad_id
    assert reconciled.status is ChangeStatus.COMPLETE
    assert reconciled.gap == "all destination receipts verified"
