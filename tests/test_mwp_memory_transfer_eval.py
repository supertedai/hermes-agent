from agent.mwp_memory_transfer_eval import EpisodeResult, evaluate


def test_memory_transfer_eval_measures_gain_and_keeps_shadow_label():
    rows = [
        EpisodeResult("a", False, False, False, False, False, False, 100),
        EpisodeResult("a", True, True, True, False, True, True, 120),
        EpisodeResult("b", False, True, False, False, False, False, 100),
        EpisodeResult("b", True, True, True, False, True, True, 110),
    ]
    report = evaluate(rows)
    assert report.transfer_gain == 0.5
    assert report.interference_rate == 0.0
    assert report.pathway_compliance == 1.0
    assert report.promotion_eligible
    assert "synthetic_shadow_fixture" in report.labels


def test_irrelevant_retrieval_blocks_promotion():
    rows = [
        EpisodeResult("a", False, False, False, False, False, False, 100),
        EpisodeResult("a", True, True, True, True, True, True, 110),
        EpisodeResult("b", False, False, False, False, False, False, 100),
        EpisodeResult("b", True, True, True, True, True, True, 110),
    ]
    assert not evaluate(rows).promotion_eligible


def test_unpaired_or_empty_results_fail_closed():
    try:
        evaluate([])
    except ValueError as exc:
        assert "episode" in str(exc)
    else:
        raise AssertionError("empty eval must fail closed")

    try:
        evaluate([EpisodeResult("a", True, True, True, False, True, True, 1)])
    except ValueError as exc:
        assert "paired" in str(exc)
    else:
        raise AssertionError("unpaired eval must fail closed")
