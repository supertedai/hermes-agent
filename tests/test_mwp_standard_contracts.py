import json

import pytest

from agent.mwp_experiment_run import Axis, ExperimentRun, Provenance, RunStatus
from agent.mwp_trace_context import new_traceparent, validate_traceparent


def test_keep_requires_measurement_rollback_and_reviewer():
    run = ExperimentRun(
        experiment_id="exp-1",
        goal_id="goal-1",
        axis=Axis.AGENT,
        status=RunStatus.KEEP,
        metric="quality",
        baseline=1,
        provenance=Provenance(source="autoresearch", verified=False),
    )
    assert "after measurement" in "; ".join(run.validate())
    assert "rollback_ref" in "; ".join(run.validate())
    assert "reviewer_verdict" in "; ".join(run.validate())


def test_valid_keep_serializes():
    run = ExperimentRun(
        experiment_id="exp-2",
        goal_id="goal-2",
        axis=Axis.SYSTEM,
        status=RunStatus.KEEP,
        metric="val_bpb",
        baseline=2.0,
        after=1.8,
        rollback_ref="git:abc123",
        reviewer_verdict="PASS",
        provenance=Provenance(source="autoresearch", source_commit="abc123"),
    ).require_valid()
    assert json.loads(json.dumps(run.as_dict()))["status"] == "KEEP"


def test_traceparent_is_format_valid_and_nonzero():
    value = new_traceparent()
    assert validate_traceparent(value)
    assert not validate_traceparent("00-" + "0" * 32 + "-" + "1" * 16 + "-01")


def test_invalid_parallelism_fails():
    run = ExperimentRun("e", "g", Axis.USER, RunStatus.PROPOSED, "m", 0, Provenance("x"), parallelism=0)
    with pytest.raises(ValueError, match="parallelism"):
        run.require_valid()
