import json
import subprocess
import sys
from pathlib import Path

from agent.mwp_holistic_gap_gate import GATES, PLANES


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_mwp_holistic_gap_gate.py"


def payload(status="COMPLETE"):
    return {
        "scope": {"target": "test", "baseline": "known-good"},
        "gates": {gate: {"status": status} for gate in GATES},
        "cross_plane": {plane: {"status": status} for plane in PLANES},
    }


def test_cli_returns_complete_json(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["verdict"] == "COMPLETE"


def test_cli_returns_nonzero_blocked(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(payload("OPEN")), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0  # OPEN is PARTIAL, not BLOCKED
    assert json.loads(proc.stdout)["verdict"] == "PARTIAL"


def test_cli_blocks_bad_input(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text("{}", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["verdict"] == "BLOCKED"
