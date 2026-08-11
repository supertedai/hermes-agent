---
name: experiment-loop
description: Use for bounded autonomous experiments; capture baseline, run isolated change, measure outcome and promote only with evidence.
---

# Bounded experiment loop

1. Read the existing BL/CAD/ADR and verify target scope.
2. Create an `ExperimentRun` with `axis`, principal/agent, metric, baseline and budget.
3. Create a unique W3C trace context and isolated worktree/environment.
4. Run one bounded experiment; no unapproved writes or deployment.
5. Record tests, provenance, reviewer verdict and rollback reference.
6. Measure a comparable `after` outcome. Do not use process exit or executor success as learning.
7. Decide `KEEP`, `DISCARD`, `BLOCK` or `ESCALATE`.
9. For Karpathy autoresearch, run the read-only promotion gate before any landing:

```bash
python3 scripts/mwp_autoresearch_promotion_gate.py
```

`OWNER_GATE` is the expected result until a canonical reviewer PASS and rollback reference are
present. The gate never copies `train.py`, commits, deploys or writes to `.12`.

Halo may annotate the trace as `halo_self_report`; it cannot approve, commit, enact or promote.
Karpathy autoresearch runs remain isolated under BL-3935 and must use this receipt contract before
any result can influence MWP, Hermes, an agent policy or the world model.

## `.15` entrypoint

Use the governed wrapper instead of invoking `train.py` directly:

```bash
python3 scripts/mwp_autoresearch_runner.py
```

It is a metadata-only dry-run by default. A training attempt requires all of:

```text
--run
--allow-training
--bl-ref BL-3935
clean checkout
NVIDIA GPU
```

The wrapper still returns `READY_GATED`; it does not grant production, MWP-authority or Hermes
write access.
