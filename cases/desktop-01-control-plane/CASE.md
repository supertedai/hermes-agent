# MWP-UOSH-001 / CASE-DESKTOP-01 — Desktop as single pane of control

## Objective

Make Hermes Desktop the controlled, metadata-first single pane of control for the existing Opus/Hermes/Symbiose system.

Desktop should expose and control existing capabilities through typed backend contracts, without becoming a second memory store, graph writer, identity store or runtime owner.

## Ownership model

- Desktop renderer owns presentation and user intent.
- Electron owns machine/runtime capabilities through the narrow bridge.
- Hermes backend/gateway owns sessions, tools, model calls and authoritative state.
- `/brukere` owns users, roles and capabilities.
- Symbiose owns its graph/memory services and server-side writer gates.
- Kanban owns durable MWP task/case state.
- Evidence ledger owns verification evidence.

## Single-pane rule

Every Desktop control must map to one of:

```text
read-only status/query
existing governed backend command
existing approved write route
owner/reviewer gate
blocked/unknown state
```

A button must never mutate local shadow state and claim that the system changed.

## Required control surfaces

- identity/user/session status
- profile/runtime/home
- model/provider/routing status
- memory layer status and promotion gates
- graph/Qdrant/GNN status and readback
- Kanban/MWP cases and dependencies
- Faber/CODEX goal state and evidence
- cron/workflow status
- topology/service registry
- approvals/owner gates
- test/readback/rollback status
- web/desktop/gateway/TUI parity

## Update safety contract

Desktop cannot accept an update that breaks Opus integration.

Every update must pass:

1. Desktop typecheck/build.
2. Gateway/RPC schema compatibility check.
3. Existing `/brukere` identity/capability tests.
4. Symbiose read/gate/readback tests.
5. Session client/durable ID lineage tests.
6. Kanban/MWP task lifecycle tests.
7. Evidence/rollback contract tests.
8. Metadata-only UI/no-leak tests.
9. Cross-surface smoke tests.
10. Canary and rollback before promotion.

Failed update behavior:

```text
hold update
→ preserve last known-good Desktop
→ show metadata-only blocker
→ do not partially migrate state
→ allow rollback
```

## Versioning

- Version the backend/RPC contract, not individual UI assumptions.
- Use capability negotiation for older runtimes.
- Keep migrations backward-readable.
- Pin the managed Desktop runtime and record source/build/runtime fingerprints.
- Do not auto-update across an unverified Opus compatibility boundary.

## Non-goals

- No direct renderer writes to users.json, memory files, graph or Qdrant.
- No Desktop-specific parallel auth or task database.
- No hidden auto-approval of owner/security/production gates.
- No UI-only success state without authoritative readback.

## Acceptance criteria

Desktop is the single pane only when every displayed control has an authoritative owner, typed route, scope, provenance, gate and readback/rollback behavior, and a failing update is held back automatically.

## Status

`PROPOSED / ARCHITECTURE-GATE`

Requires mapping to existing CAD-A/C/G/O/V/Z/Ø, BL/ADR records and the MWP service registry before implementation.
