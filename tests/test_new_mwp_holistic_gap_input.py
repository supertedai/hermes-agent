import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "new_mwp_holistic_gap_input.py"


def test_generator_creates_fail_closed_input(tmp_path):
    out = tmp_path / "input.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--target', 'neo4j-schema', '--baseline', 'known-good', '--output', str(out)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    payload = json.loads(out.read_text())
    assert payload['scope']['target'] == 'neo4j-schema'
    assert all(x['status'] == 'OPEN' for x in payload['gates'].values())
    assert all(x['status'] == 'OPEN' for x in payload['cross_plane'].values())
    assert payload['writes_allowed'] is False
