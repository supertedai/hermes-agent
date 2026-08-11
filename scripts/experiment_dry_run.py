"""Read-only ExperimentRun dry-run: no files, graph writes or deployment."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.mwp_experiment_run import Axis, ExperimentRun, Provenance, RunStatus

run = ExperimentRun(
    experiment_id="dry-run-standard-stack-001",
    goal_id="mwp-uosh-standard-stack",
    bl_ref="BL-3932",
    axis=Axis.SYSTEM,
    status=RunStatus.KEEP,
    metric="contract_test_pass_rate",
    baseline=0,
    after=1,
    change_ref="local:standard-contracts",
    rollback_ref="git:explicit-file-revert",
    reviewer_verdict="PASS",
    outcome="contract tests passed; no runtime side effects",
    provenance=Provenance(
        source="mwp-local-dry-run",
        source_commit="uncommitted-scope-only",
        verified=True,
        traceparent="",
    ),
    evidence={"tests": "9 passed", "side_effects": "none"},
)
run.require_valid()
print(json.dumps({
    "status": "PASS",
    "experiment_id": run.experiment_id,
    "axis": run.axis.value,
    "metric": run.metric,
    "baseline": run.baseline,
    "after": run.after,
    "reviewer_verdict": run.reviewer_verdict,
    "rollback_ref": run.rollback_ref,
    "side_effects": "none",
}, sort_keys=True))
