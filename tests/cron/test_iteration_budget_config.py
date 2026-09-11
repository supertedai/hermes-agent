"""Regression coverage for cron iteration-budget boundary normalization."""

import pytest

from cron.scheduler import _resolve_cron_max_iterations


def test_cron_iteration_budget_accepts_int_and_decimal_string():
    assert _resolve_cron_max_iterations(12) == 12
    assert _resolve_cron_max_iterations(" 12 ") == 12


def test_cron_iteration_budget_defaults_when_missing():
    assert _resolve_cron_max_iterations(None) == 500


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "", "abc", "1.5"])
def test_cron_iteration_budget_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="max_turns"):
        _resolve_cron_max_iterations(value)
