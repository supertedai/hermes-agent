import json

import pytest

from agent.mwp_flyby_continuation import (
    compact_readback,
    initial_state,
    load_checkpoint,
    next_batch,
    save_checkpoint,
)


def test_continuation_batches_and_resume(tmp_path):
    records = [{"id": f"s-{i}", "title": f"thread {i}", "content": "private raw payload"} for i in range(5)]
    state = initial_state("flyby-continue-1", ["original", "continuation"])

    first, state = next_batch(records, state, batch_size=2)
    assert [item["id"] for item in first] == ["s-0", "s-1"]
    assert state.cursor == 2
    assert state.status == "OPEN"

    checkpoint = tmp_path / "checkpoint.json"
    save_checkpoint(checkpoint, state)
    restored = load_checkpoint(checkpoint)
    assert restored is not None
    assert restored == state

    second, state = next_batch(records, restored, batch_size=2)
    third, state = next_batch(records, state, batch_size=2)
    assert [item["id"] for item in second] == ["s-2", "s-3"]
    assert [item["id"] for item in third] == ["s-4"]
    assert state.status == "COMPLETE"


def test_readback_is_metadata_only_and_bounded():
    state = initial_state("bounded", ["a", "b"], total=1)
    rendered = compact_readback(
        state,
        [{"id": "x", "title": "small", "content": "DO NOT RETURN THIS", "secret": "DO NOT RETURN THIS"}],
    )
    parsed = json.loads(rendered)
    assert parsed["batch"] == [{"id": "x", "title": "small"}]
    assert "content" not in rendered
    assert "secret" not in rendered

    compact = compact_readback(state, [{"id": str(i), "title": "x"} for i in range(100)], max_chars=256)
    assert len(compact) <= 256
    assert json.loads(compact)["readback_truncated"] is True


def test_invalid_batch_size_and_cursor_are_rejected():
    state = initial_state("x", [])
    with pytest.raises(ValueError):
        next_batch([], state, batch_size=0)
    with pytest.raises(ValueError):
        next_batch([], state.__class__("x", (), cursor=2), batch_size=1)
