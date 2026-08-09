# ADR-HERMES-SURFACE-BACKPLANE-001 — Web and Desktop as shared-backplane surfaces

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`
**Parent:** `CAD-HERMES-SURFACE-BACKPLANE-001`

## Decision

`.14` web GUI, PC/laptop Desktop, TUI and gateway use a common canonical auth/session and Hermes engine route. Their UI state is a projection; the backplane owns cross-surface session/event continuity.

The architecture distinguishes:

```text
surface visibility
≠ session identity
≠ backend authority
≠ writer readiness
≠ runtime effect
```

No surface may infer backend authority from a successful login alone.

## Web/Desktop migration decision

Keep the existing web GUI as the operational baseline until `BL-HERMES-SURFACE-BACKPLANE-001` and P1 thread parity are complete. Do not use a frontend replacement to work around an unresolved broker/session authority split.

The Desktop front layer is a later strangler/canary migration over the same backend contracts, not a new auth, session or memory system. Cutover requires parity, health, compatibility and rollback receipts.

## Consequences

- one user can move between web, Desktop and laptop without separate memory silos;
- all learning and memory events enter through Hermes and canonical ingest;
- local/offline queues require idempotency and explicit replay status;
- surface drift is visible as `STALE`, `DIVERGED` or `UNKNOWN`;
- a known-good Desktop remains the rollback baseline.

## Rejected alternatives

- independent `.14` memory database;
- separate web-only learning writer;
- direct Desktop-to-graph writes;
- treating login success as authority proof;
- destructive migration of the existing Desktop/session baseline.

Runtime activation remains gated by `BL-HERMES-SURFACE-BACKPLANE-001`.
