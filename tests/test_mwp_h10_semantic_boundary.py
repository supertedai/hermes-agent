from agent.mwp_h10_semantic_boundary import H10Verdict, validate_theory_home_record


def valid():
    return {"record_id":"r1","package_id":"p1","home_class":"H10","record_layer":"THEORY","claim_status":"THEORY_CLAIM","runtime_status":"NOT_APPLICABLE","source_ref":"src","provenance_ref":"prov","owner_id":"morten","review_status":"PENDING"}


def test_valid_semantic_record():
    assert validate_theory_home_record(valid()) == (H10Verdict.COMPLETE, ())


def test_missing_or_invalid_is_fail_closed():
    r=valid(); r.pop("record_layer")
    assert validate_theory_home_record(r)[0] == H10Verdict.UNCLASSIFIED
    r=valid(); r["record_layer"]="UNKNOWN"
    assert validate_theory_home_record(r)[0] == H10Verdict.BLOCKED


def test_methodology_is_distinct_record_layer():
    r=valid(); r["record_layer"]="METHODOLOGY"; r["claim_status"]="METHODOLOGY"
    assert validate_theory_home_record(r) == (H10Verdict.COMPLETE, ())


def test_supporting_artifact_is_not_runtime_authority():
    r=valid(); r["record_layer"]="SUPPORTING_ARTIFACT"; r["runtime_status"]="NOT_APPLICABLE"
    assert validate_theory_home_record(r) == (H10Verdict.COMPLETE, ())



def test_runtime_and_validation_promotion_need_receipts():
    r=valid(); r["record_layer"]="LIVE_RUNTIME_EVIDENCE"; r["runtime_status"]="LIVE_VERIFIED"
    assert validate_theory_home_record(r)[0] == H10Verdict.BLOCKED
    r["runtime_receipt_ref"]="rr1"
    r["claim_status"]="VALIDATED"
    assert validate_theory_home_record(r)[0] == H10Verdict.BLOCKED
    r["evaluation_receipt_ref"]="er1"
    assert validate_theory_home_record(r)[0] == H10Verdict.COMPLETE


def test_prediction_and_evaluation_artifacts_are_distinct_layers():
    r=valid(); r["record_layer"]="PREDICTION_ARTIFACT"; r["claim_status"]="PREDICTION"
    assert validate_theory_home_record(r) == (H10Verdict.COMPLETE, ())
    r=valid(); r["record_layer"]="EVALUATION_ARTIFACT"; r["claim_status"]="VALIDATION_PENDING"
    assert validate_theory_home_record(r) == (H10Verdict.COMPLETE, ())
