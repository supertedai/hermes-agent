from scripts.mwp_autoresearch_promotion_gate import evaluate_receipt


def test_candidate_without_reviewer_is_owner_gate():
    result = evaluate_receipt({
        "bl": "BL-3935",
        "decision": "promote_candidate",
        "reviewer": "none",
        "candidate_commit": "abc",
        "val_bpb_observed": 1.2,
    })
    assert result["status"] == "OWNER_GATE"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "canonical reviewer PASS missing" in blockers
    assert "rollback_ref missing" in blockers


def test_candidate_with_all_receipts_is_review_ready_but_side_effect_free():
    result = evaluate_receipt({
        "bl": "BL-3935",
        "decision": "promote_candidate",
        "reviewer": "PASS",
        "candidate_commit": "abc",
        "val_bpb_observed": 1.2,
        "rollback_ref": "run:abc/train.py",
    })
    assert result == {
        "experiment_id": "",
        "status": "REVIEW_READY",
        "blockers": [],
        "side_effects": "none",
    }


def test_malformed_numeric_receipt_stays_owner_gate():
    result = evaluate_receipt({
        "bl": "BL-3935",
        "decision": "promote_candidate",
        "reviewer": "PASS",
        "candidate_commit": "abc",
        "val_bpb_observed": "nan",
        "rollback_ref": "run:abc/train.py",
    })
    assert result["status"] == "OWNER_GATE"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "measured val_bpb missing" in blockers


def test_boolean_metric_stays_owner_gate():
    result = evaluate_receipt({
        "bl": "BL-3935",
        "decision": "promote_candidate",
        "reviewer": "PASS",
        "candidate_commit": "abc",
        "val_bpb_observed": True,
        "rollback_ref": "run:abc/train.py",
    })
    assert result["status"] == "OWNER_GATE"
