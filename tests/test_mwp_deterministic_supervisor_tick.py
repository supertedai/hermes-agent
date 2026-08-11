import importlib.util
import json
from pathlib import Path

path = Path(__file__).parents[1] / "scripts" / "mwp_deterministic_supervisor_tick.py"
spec = importlib.util.spec_from_file_location("supervisor", path)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_blocked_closeout_cannot_claim():
    result = {"ok": True, "stdout": json.dumps({"status": "OPEN", "blocker_count": 10})}
    assert mod._closeout_allows_claim(result) is False


def test_complete_closeout_allows_claim():
    result = {"ok": True, "stdout": json.dumps({"status": "COMPLETE", "blocker_count": 0})}
    assert mod._closeout_allows_claim(result) is True


def test_malformed_or_failed_closeout_fails_closed():
    assert mod._closeout_allows_claim({"ok": False, "stdout": ""}) is False
    assert mod._closeout_allows_claim({"ok": True, "stdout": "not-json"}) is False
