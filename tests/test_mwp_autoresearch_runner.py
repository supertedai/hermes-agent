import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mwp_autoresearch_runner.py"


def run(*args: str) -> tuple[int, dict[str, object]]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)
    return proc.returncode, json.loads(proc.stdout)


def test_autoresearch_default_is_dry_run():
    code, result = run()
    assert code == 0
    assert result["status"] == "DRY_RUN_PASS"
    assert result["training"] is False
    assert result["side_effects"] == "none"


def test_training_is_blocked_without_explicit_bl_and_consent():
    code, result = run("--run")
    assert code == 2
    assert result["status"] == "BLOCKED"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert any("BL-3935" in item for item in blockers)
    assert any("allow-training" in item for item in blockers)
    assert result["side_effects"] == "none"
