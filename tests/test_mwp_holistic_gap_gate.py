from agent.mwp_holistic_gap_gate import GATES, PLANES, evaluate_holistic_gap_gate


def base(status='COMPLETE'):
    return {
        'scope': {'target': 'memory-change', 'baseline': 'known-good'},
        'gates': {gate: {'status': status} for gate in GATES},
        'cross_plane': {plane: {'status': status} for plane in PLANES},
    }


def test_gate_blocks_missing_scope_or_gate():
    result = evaluate_holistic_gap_gate(scope={}, gates={}, cross_plane={})
    assert result['verdict'] == 'BLOCKED'
    assert result['writes_performed'] is False


def test_gate_is_partial_for_open_cross_plane():
    data = base()
    data['cross_plane']['gnn'] = {'status': 'OPEN'}
    result = evaluate_holistic_gap_gate(**data)
    assert result['verdict'] == 'PARTIAL'
    assert 'G4:gnn:OPEN' in result['partial']


def test_gate_completes_only_when_all_evidence_is_complete():
    result = evaluate_holistic_gap_gate(**base())
    assert result['verdict'] == 'COMPLETE'
    assert result['blockers'] == []
    assert result['partial'] == []
    assert result['raw_payload_included'] is False


def test_gate_rejects_write_mode():
    result = evaluate_holistic_gap_gate(**base(), writes_allowed=True)
    assert result['verdict'] == 'BLOCKED'
    assert 'writes_allowed_must_remain_false_for_metadata_gate' in result['blockers']
