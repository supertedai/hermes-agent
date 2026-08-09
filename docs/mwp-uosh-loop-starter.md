# MWP-UOSH — fail-closed closeout loop starter

## Purpose

`agent/mwp_loop_starter.py` keeps a governed closeout alive across verification
 ticks. It prevents a green subtask, a passing backend test, or an observe-only
 tick from being reported as completion of the whole job.

## Authority and side effects

- The existing Faber goal registry, Kanban board, and coverage matrix remain the
  authorities.
- The starter creates no user, agent, role, lease, capability, or route.
- It does not build, review, commit, land, start services, or activate a
  scheduler.
- Its optional output is metadata-only latest readback, written atomically.

## Tick contract

The caller supplies a `tick(number) -> LoopTick` callback. Each tick must read
current authoritative state and return:

- `readback`: metadata-only coverage/control status;
- `complete=True` only when the **whole** closeout/matrix is closed;
- `blocker`: an explicit owner/security/runtime/evidence blocker;
- `next_action`: the next permitted action.

A completed backend/Faber candidate-test slice must return `complete=False` if
master coverage still has open rows. The next tick then runs automatically.

## Stop contract

The loop may stop only with one of these statuses:

- `COMPLETE`: the caller proved the entire workflow is closed;
- `BLOCKED`: an explicit blocker or owner gate exists;
- `FAILED`: a tick raised an exception, recorded without pretending success;
- `LIMIT_REACHED`: a process safety bound fired; this is not success and can be
  resumed from the persisted readback.

`max_ticks` and `max_seconds` are process-safety bounds, not completion rules.
They prevent an unbounded daemon from consuming a process forever while keeping
the semantic rule that no partial success closes the job.

## Intended integration shape

```python
from agent.faber_observe import observe
from agent.mwp_loop_starter import LoopTick, start_loop


def tick(number: int) -> LoopTick:
    observed = observe(registry, repo_paths=repo_paths)
    matrix = read_master_coverage_metadata()  # existing canonical readback
    blocker = first_open_gate(matrix)
    return LoopTick(
        readback={
            "tick": number,
            "faber_goals": observed.goals,
            "preflight_clear": observed.preflight_clear,
            "coverage_status": matrix.status,
        },
        complete=(matrix.status == "COMPLETE" and not blocker),
        blocker=blocker,
        next_action="continue next verification slice" if not blocker else "resolve gate",
    )

result = start_loop(
    "mwp-uosh-master-coverage",
    tick,
    readback_path=".../mission-control.json",
)
```

The typed Desktop route remains blocked until its principal/capability,
role/provider receipt, lease, reviewer, evidence/readback and rollback contract
is actually verified. The loop must surface that as `BLOCKED`, not silently
route around it.
