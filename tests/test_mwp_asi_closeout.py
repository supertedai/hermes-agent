from agent.mwp_asi_alignment_registry import ASIStatus, build_status_quo
from agent.mwp_asi_closeout import evaluate_closeout


def test_closeout_stays_open_on_unverified_registry_and_receipts():
    result = evaluate_closeout(build_status_quo(), ("VERIFIED", "BLOCKED", "UNVERIFIED"))
    assert result.status == "OPEN"
    assert result.continue_loop is True
    assert any("world-model-hub-alignment" in blocker for blocker in result.blockers)
    assert "receipt:BLOCKED" in result.blockers


def test_closeout_requires_receipts():
    result = evaluate_closeout(build_status_quo(), ())
    assert result.status == "OPEN"
    assert "receipts:missing" in result.blockers
