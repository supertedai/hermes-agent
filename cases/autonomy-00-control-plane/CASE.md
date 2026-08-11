# MWP-UOSH-001 / CASE-AUTONOMY-00 — Autonomy Control Plane foundation

## Purpose

Create the smallest durable control-plane contract required for bounded full automation across the three ASI axes:

```text
per-user
system/Cortex worldmodel
per-agent/steward
```

This is the foundation beneath Desktop, memory, ingest, cognition, Kanban and workers.

## Hard dependencies

- `CASE-IDENTITY-01`: Morten owner path versus Joakim authenticated multiuser path.
- `/brukere`: canonical user/role/capability authority.
- `/symbiose`: existing Symbiose service/graph surface.
- Kanban: candidate canonical durable task/case state.
- Existing `code_workflow`: preflight/gates/goal lifecycle.
- Existing `verification_evidence`: evidence ledger.

## Control-plane record

Every automated unit must carry:

```text
mwp_id
case_id
task_id
principal_id
axis: user | system | agent
profile
session_id
client_session_id
durable_session_id
project/domain
owner
source_refs
cad_refs
adr_refs
bl_refs
dependencies
scope
risk/blast_radius
current_state
required_gate
evidence_refs
rollback_ref
next_permitted_action
```

## State machine

```text
DISCOVERY
→ CLASSIFIED
→ PLANNED
→ PREFLIGHT
→ READY
→ CLAIMED
→ RUNNING
→ VERIFYING
→ REVIEW
→ CLOSED
```

Stop states:

```text
BLOCKED
OWNER_GATE
SECURITY_GATE
ROLLBACK_REQUIRED
STALE
CONFLICT
```

## First implementation slice

Read-only/metadata-only adapter and contract tests for:

1. stable MWP/case/task IDs;
2. three-axis/principal scope;
3. dependency readiness;
4. gate decision;
5. evidence references;
6. parent cannot advance while child is blocked/owner-gated;
7. metadata-only master readback;
8. no scheduler activation and no graph/memory/Qdrant writes.

## Full automation sequence after foundation

```text
Control Plane
→ Identity/session authority
→ Kanban task authority
→ Evidence/provenance
→ Dependency-aware orchestrator
→ Scoped workers/worktrees
→ Verification/read-after-write
→ Rollback/recovery
→ Desktop control surface
→ Ingest/memory loops
→ Cognition/learning loops
→ Graph/Qdrant/GNN promotion
→ Durable scheduler activation
```

## Acceptance criteria

- No task can execute without principal/axis/scope classification.
- No parent advances past a blocked or owner-gated child.
- Every outcome has evidence and a next permitted action.
- No authority is duplicated into the UI.
- Existing Morten owner path and Joakim multiuser path remain distinguishable.
- The adapter is side-effect free until later gate-approved execution.

## Evidence

- [x] `agent/mwp_control_plane.py` written as a side-effect-free deterministic contract adapter.
- [x] `tests/test_mwp_control_plane.py` written for dependency, gate, duplicate-ID, blocked-state and metadata-only invariants.
- [x] Edit-time syntax/lint gate passed for the new Python files.
- [x] First read-only 13-step dry-run verified against existing readers; 13 stages represented, no executor invoked.
- [x] `agent/mwp_autocoder_entrypoint.py` added as a thin role-separated wrapper-plan contract; it does not call models or mutate Kanban/evidence/runtime.
- [x] Required roles are explicit: design, build, review; missing role bindings block.
- [x] Runtime-unverified state blocks executor permission; `runtime_verified=True` only produces a plan permission, not execution.
- [x] Canonical tests: 2 files, 25 tests passed, 0 failed.

## Status

`FOUNDATION SUBPACKAGE CLOSED / ROLE-PROVIDER RESOLUTION OWNER_GATE`

The side-effect-free control-plane foundation and wrapper-plan contract are closed as a tested subpackage. The parent case and MWP remain open because live Sol/Luna/Claude model-provider bindings are not yet verified.

## Closed subpackage receipt

```text
scope:          control-plane foundation + wrapper-plan contract
implementation: agent/mwp_control_plane.py + agent/mwp_autocoder_entrypoint.py
invariants:     IDs, axis/principal scope, dependencies, gates, evidence refs, parent blocking
side_effects:   none
runtime:        no executor invoked; no scheduler/graph/memory/Qdrant write
verification:   80-test MWP baseline passed; targeted control-plane tests passed
closeout:       CLOSED as subpackage, not parent case
```

## Next permitted action

Resolve and record actual Sol/Luna/Claude model/provider bindings from live configuration/catalog/runtime evidence. Do not treat role labels as live model proof and do not invoke an executor.
