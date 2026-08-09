# ASI observability and experiment workflow

**Authorities:** MWP-UOSH-001, BL-3923 (Halo), BL-3932 (OTel trace), BL-3935 (autoresearch).

## Loop

```text
DISCOVER
  read BL/CAD/ADR/lease and current topology
MAP
  set axis=user|system|agent, principal, agent, workflow and scope
TRACE
  create W3C traceparent and OTel metadata spans
BASELINE
  capture metric and evidence refs before change
SANDBOX
  use isolated worktree/environment and bounded time/parallelism
RUN
  execute only the approved diagnostic or experiment lane
OBSERVE
  Halo may diagnose traces; Halo cannot approve, commit or enact
VERIFY
  tests, provenance, reviewer and read-after-write/read-after-runtime
DECIDE
  KEEP | DISCARD | BLOCK | ESCALATE
MEASURE
  record before/after outcome, not executor success
LEARN
  promote only a validated learning event with scope and rollback
```

## Holistic cross-plane insertion

For every MWP/CAD/ADR/BL step, load and execute:

```text
docs/mwp-holistic-automatic-gap-gate-v1.json
```

Create a fail-closed input automatically for each step:

```text
python3 scripts/new_mwp_holistic_gap_input.py \
  --target TARGET \
  --baseline BASELINE \
  --output .mwp/holistic-gate-input.json
```

Then run the executable preflight:

```text
python3 scripts/run_mwp_holistic_gap_gate.py .mwp/holistic-gate-input.json
```

The generated input starts `OPEN` and cannot close a workflow without evidence updates.

The executable preflight is:

```text
python3 scripts/run_mwp_holistic_gap_gate.py INPUT.json
```

It emits JSON only, performs no writes, returns `0` for `COMPLETE`/`PARTIAL` and returns non-zero for `BLOCKED`. Run it before `RUN` and again before `DECIDE`.

Apply the gate sequence after `MAP` and again before `DECIDE`:

```text
G0 scope/baseline
G1 industry baseline
G2 SOTA review
G3 ASI/cutting-edge review
G4 Neo4j ↔ Qdrant ↔ GNN ↔ Hermes ↔ surface compatibility
G5 tests/latency/quality/drift
G6 authenticated live evidence/read-after-write/rollback
G7 closeout decision
```

The same workflow must cover schema/migrations, graph nodes/edges, Qdrant collections, GNN models, providers, ingest envelopes, CRUD propagation, surfaces, learning and restore. A provider, schema, inventory or green unit test is never sufficient by itself.

## Gates

| Gate | Requirement | Failure result |
|---|---|---|
| identity | principal/session/agent resolved | BLOCK |
| BL scope | existing BL is actionable and target is explicit | BLOCK |
| trace | unique traceparent and job correlation | BLOCK |
| sandbox | isolated worktree and bounded resources | BLOCK |
| security | secret/injection/permission checks pass | BLOCK |
| reviewer | canonical PASS for code or policy change | BLOCK/ESCALATE |
| provenance | source/config/artifact refs available | BLOCK |
| outcome | baseline and after are comparable | BLOCK |
| promotion | owner/approved gate where required | ESCALATE |

## Safe default

A missing receipt keeps the lane `OPEN` or `BLOCKED`; it never closes the parent goal and never
turns an unverified observation into a fact.
