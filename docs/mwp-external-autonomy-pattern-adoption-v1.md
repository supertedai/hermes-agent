# External autonomy-pattern adoption — MWP-UOSH-001

Status: `IMPLEMENTED_LOCALLY_READ_ONLY`

This is a fit/adoption record, not an external-project endorsement and not a
runtime authority. Existing MWP/Kanban, evidence, worktree, scheduler and
rollback surfaces remain canonical.

| Pattern | Decision | Local target | Gap/status |
|---|---|---|---|
| Explicit mission contract | ADOPT | `agent/mwp_autonomy_envelope.py` | Implemented as metadata-only envelope pointing to existing task authority |
| Autonomy levels L0–L4 | ADAPT | `AutonomyLevel` | Implemented; L4 requires explicit owner gate |
| Dependency graph | ADAPT | `validate_dependency_graph` | Implemented with unknown-reference and cycle fail-closed checks |
| Evidence ledger | ALREADY COVERED + ADAPT | existing receipts/change ledger + `EvidenceRef` | Envelope now requires named evidence refs where the caller declares them |
| Restart/checkpoint recovery | ADAPT | `checkpoint_ref`, `RecoveryMode` | Contract is present; scheduler/restart authority remains an open runtime gate |
| Rollback | ALREADY COVERED + ENFORCE | existing rollback refs + envelope | rollback-required state cannot proceed without a rollback reference |
| Isolated worktree | ALREADY COVERED | existing Hermes/MWP worktree primitives | No duplicate worktree manager added |
| Independent verification | ALREADY COVERED | existing verification evidence and closeout | No self-approval path added |
| Codebase knowledge graph | SHADOW ONLY | external read-only analysis candidate | Must not replace canonical CAD/ADR/BL or graph authority |
| Community skills | SELECTIVE | existing skill governance | Audit/install one skill at a time; no bulk import |
| CEO/swarm topology | ALREADY COVERED | Cortex/Faber/Sol/Luna/Claude/fleet routing | Main gap is live role/provider/lease evidence, not more agent names |

## Verified gap set after audit

The largest remaining gaps are live/runtime rather than missing abstractions:

1. authenticated CAD → ADR → BL → git → daemon → runtime receipt;
2. principal/device/session/tenant parity across Desktop and backend;
3. canonical task child/dependency/lease/heartbeat read-after-write;
4. chat ↔ Cortex ↔ shared world-model round trip;
5. live lateral agent handoff with scope, consent and trace;
6. measured learning promotion and rollback;
7. continuous freshness/drift scheduler with canonical destination;
8. cross-domain capability evaluation.

The new envelope addresses only the **contract-shape gap**. It does not claim
that any of these live authority gates are closed.

## Runtime adapter

`agent/mwp_autonomy_adapter.py` is the bounded integration seam for the existing
`ControlTask` contract. It projects a task into a `MissionEnvelope` and returns a
metadata-only `MissionReadback`; it does not create tasks, leases, writers,
schedulers or runtime authority. Evidence is opened only when callers pass an
explicit `verified_evidence_refs` set. Declared-but-unverified refs remain
blocked.

## Safety boundary

The envelope and adapter are deliberately free of persistence, scheduling,
model calls, network calls and external writes. They project mission metadata
and return a fail-closed readback. Integration with the real task authority
must preserve owner, identity, provenance, read-after-write and rollback gates.
