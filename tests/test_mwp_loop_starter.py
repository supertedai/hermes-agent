from agent.mwp_loop_starter import LoopPolicy, LoopStatus, LoopTick, start_loop


def test_loop_continues_after_substep_until_whole_job_is_complete(tmp_path):
    calls = []
    readback = tmp_path / "mission-control.json"

    def tick(number):
        calls.append(number)
        return LoopTick(
            readback={"coverage": number, "status": "partial" if number < 3 else "closed"},
            complete=number == 3,
            next_action="continue coverage" if number < 3 else "none",
        )

    result = start_loop(
        "mwp-closeout",
        tick,
        policy=LoopPolicy(max_ticks=10),
        readback_path=readback,
    )

    assert result.status is LoopStatus.COMPLETE
    assert result.ticks == 3
    assert calls == [1, 2, 3]
    assert result.last_readback["status"] == "closed"
    assert '"status": "COMPLETE"' in readback.read_text(encoding="utf-8")


def test_open_gate_is_logged_but_does_not_stop_the_loop(tmp_path):
    calls = []

    def tick(number):
        calls.append(number)
        if number < 3:
            return LoopTick(
                readback={"ledger": "OPEN", "lane": number},
                blocker="git/graph/obsidian receipts still open",
                next_action="continue independent topology/world-model lanes",
                continue_loop=True,
            )
        return LoopTick(readback={"ledger": "OPEN", "lane": number}, complete=True)

    result = start_loop("open-ledger", tick, policy=LoopPolicy(max_ticks=5), readback_path=tmp_path / "readback.json")

    assert result.status is LoopStatus.COMPLETE
    assert result.ticks == 3
    assert calls == [1, 2, 3]


def test_loop_stops_only_on_explicit_blocker(tmp_path):
    calls = []

    def tick(number):
        calls.append(number)
        return LoopTick(
            readback={"route": "blocked"},
            blocker="typed Desktop route not verified",
            next_action="finish backend/runtime evidence first",
        )

    result = start_loop("faber-route", tick, readback_path=tmp_path / "readback.json")

    assert result.status is LoopStatus.BLOCKED
    assert result.ticks == 1
    assert calls == [1]
    assert result.blocker == "typed Desktop route not verified"


def test_tick_failure_becomes_durable_failed_state():
    def tick(_number):
        raise RuntimeError("boom")

    result = start_loop("failure", tick, policy=LoopPolicy(max_ticks=2))

    assert result.status is LoopStatus.FAILED
    assert result.ticks == 1
    assert result.blocker == "tick failed: RuntimeError"


def test_safety_limit_does_not_claim_success():
    def tick(number):
        return LoopTick(readback={"tick": number}, complete=False)

    result = start_loop("bounded", tick, policy=LoopPolicy(max_ticks=2))

    assert result.status is LoopStatus.LIMIT_REACHED
    assert result.ticks == 2
    assert result.blocker == "tick limit reached before whole-job completion"


def test_invalid_policy_is_rejected():
    try:
        LoopPolicy(max_ticks=0)
    except ValueError as exc:
        assert str(exc) == "max_ticks must be at least 1"
    else:
        raise AssertionError("invalid loop policy must fail closed")
