from agent.mwp_coverage_matrix import (
    CoverageRow,
    CoverageStatus,
    build_matrix,
    matrix_tick,
    validate_metadata_payload,
)
from agent.mwp_loop_starter import LoopPolicy, LoopStatus, LoopTick, start_loop


def row(control, status=CoverageStatus.CONNECTED):
    return CoverageRow(
        surface="Desktop",
        control=control,
        authority="Hermes backend",
        route="GET /api/status",
        scope="profile/session",
        readback="authoritative readback status",
        rollback="no mutation; stop on error",
        test="tests/test_control.py::test_status",
        status=status,
    )


def test_matrix_remains_open_while_any_gate_is_open():
    matrix = build_matrix("MWP-UOSH-001", (row("Faber", CoverageStatus.BLOCKED_UNWIRED), row("Config")))

    assert matrix.status is CoverageStatus.OPEN
    assert not matrix.complete
    assert matrix.open_rows == 1
    assert matrix.connected_rows == 1
    assert matrix_tick(matrix)["complete"] is False


def test_matrix_can_complete_only_when_all_rows_are_closed():
    matrix = build_matrix("MWP-UOSH-001", (row("Faber"), row("Config", CoverageStatus.CONNECTED_READ_ONLY)))

    assert matrix.status is CoverageStatus.CONNECTED
    assert matrix.complete
    assert matrix_tick(matrix)["complete"] is True


def test_matrix_readback_drives_continuation_loop_until_all_rows_close():
    states = [
        (CoverageStatus.OPEN, ""),
        (CoverageStatus.CONNECTED, ""),
    ]

    def tick(number):
        status, blocker = states[number - 1]
        matrix = build_matrix("MWP-UOSH-001", (row("Faber", status),))
        readback = matrix_tick(matrix, blocker=blocker)
        return LoopTick(
            readback=readback,
            complete=bool(readback["complete"]),
            blocker=blocker,
            next_action="continue matrix verification" if not readback["complete"] else "none",
        )

    result = start_loop("matrix-closeout", tick, policy=LoopPolicy(max_ticks=3))

    assert result.status is LoopStatus.COMPLETE
    assert result.ticks == 2


def test_duplicate_rows_fail_closed():
    try:
        build_matrix("MWP-UOSH-001", (row("same"), row("same")))
    except ValueError as exc:
        assert str(exc) == "duplicate surface/control pair in coverage matrix"
    else:
        raise AssertionError("duplicate coverage rows must be rejected")


def test_connected_row_must_name_readback():
    try:
        CoverageRow(
            surface="Desktop",
            control="Config",
            authority="backend",
            route="GET /api/config",
            scope="profile",
            readback="returned value",
            rollback="stop",
            test="test_config",
            status=CoverageStatus.CONNECTED,
        )
    except ValueError as exc:
        assert str(exc) == "CONNECTED row must name readback evidence"
    else:
        raise AssertionError("connected rows without readback evidence must block")


def test_metadata_validator_rejects_private_payloads():
    payload = {
        "surface": "Desktop",
        "control": "Config",
        "authority": "backend",
        "route": "GET /api/config",
        "scope": "profile",
        "readback": "status readback",
        "rollback": "stop",
        "test": "test_config",
        "status": "CONNECTED",
        "raw_output": "must not be present",
    }
    try:
        validate_metadata_payload(payload)
    except ValueError as exc:
        assert "raw/private fields" in str(exc)
    else:
        raise AssertionError("raw payload must be rejected")
