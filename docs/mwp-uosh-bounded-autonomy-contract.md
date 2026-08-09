# MWP-UOSH-001 — Bounded autonomy contract

## Decision

`MWP-UOSH-001` uses bounded autonomous execution.

The system may execute automatically inside an approved, scoped and reversible work package. It must stop and emit a metadata-only owner gate for identity, authority, security, governance, production, irreversible or otherwise out-of-scope actions.

## Automatic lane

The orchestrator may automatically:

- discover and classify sources;
- map existing CAD/ADR/BL/Git/graph records;
- select the next dependency-ready case;
- claim one scoped task through the canonical task authority;
- create/use an isolated worktree;
- run approved workers with bounded permissions, timeout and retry limits;
- collect verification evidence;
- run tests and read-after-write/restart checks;
- update task/case state;
- execute reversible R0/R1/R2 actions when pre-approved;
- produce metadata-only master readback;
- stop, block, pause, retry or roll back according to policy.

## Mandatory stop gates

The orchestrator must not cross these without explicit owner/approved authority:

- missing or contradictory user/principal/session identity;
- unknown capability or role authority;
- new or unadopted CAD/ADR/BL decision;
- dirty target with unowned changes;
- production/deployment/live-actuation;
- graph/Qdrant/memory write without canonical writer, provenance, idempotency and readback;
- security, secret, privacy or cross-user scope uncertainty;
- irreversible mutation or destructive cleanup;
- failed rollback/readback/restart verification;
- reviewer-required R3/R4/R5 action.

## Canonical existing surfaces

- `/brukere` and canonical `users.json` remain the user/role/capability authority.
- `/symbiose` and existing Symbiose services remain the Symbiose UI/service surface.
- Kanban is the candidate canonical MWP task/case state authority.
- Existing Hermes `code_workflow`, verification evidence, scheduler, worktree and rollback primitives must be reused.
- No parallel user store, task database, memory store, graph writer or scheduler may be created.

## 13-step workflow gate contract

The existing 13 top-level steps remain unchanged for compatibility. The
bounded-autonomy gates are explicit inside four existing steps:

| Step | Required contract |
|---|---|
| `bl_gate` | MissionEnvelope, CAD/ADR/BL mapping, principal/tenant/scope, dependency graph, rollback reference |
| `claim_and_lease` | preclaim policy, verified evidence, dependency readiness, canonical claim, lease/heartbeat |
| `governance` | authority/policy verdict, reviewer/owner gate, no self-approval |
| `postcommit_readback` | implementation, scoped test, runtime/read-after-write, provenance, outcome, rollback proof, CAD/ADR/BL projection |

A task must not move from `bl_gate` to `claim_and_lease` without the
MissionEnvelope and dependency/evidence inputs. A task must not move to
`CLOSED` without the postcommit readback contract.


```text
implementation
+ scoped test
+ runtime/read-after-write
+ provenance
+ dependency/parent proof
+ rollback proof
+ reviewer/owner gate where required
```

`executor success`, `recorded=true`, tool availability, process existence or configuration declaration is not sufficient.
