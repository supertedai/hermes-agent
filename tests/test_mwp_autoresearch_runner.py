import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mwp_autoresearch_runner.py"
AUTORESEARCH_REPO = ROOT.parent / "karpathy-autoresearch"

# The runner defaults to a sibling checkout of the autoresearch repo and reports
# BLOCKED before it can dry-run when that checkout is absent. Present on the .15
# project host, absent in this repo -- an environment precondition, not a defect.
pytestmark = pytest.mark.skipif(
    not AUTORESEARCH_REPO.is_dir(),
    reason=f"sibling checkout absent: {AUTORESEARCH_REPO}",
)


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
