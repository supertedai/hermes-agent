# CAD-HERMES-SURFACE-BACKPLANE-001 — Shared Hermes surfaces

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED`
**Parent:** `MWP-UOSH-001`
**Related:** `CAD-HERMES-MEMORY-FABRIC-001`, `CAD-HERMES-INGEST-001`

## Decision

The Hermes web GUI on `.14`, Desktop on PC/laptop and other channels are presentation/control surfaces over one canonical session and backplane. They must not become separate memory, learning or authority islands.

```text
surface
  → canonical auth/session broker
  → Hermes engine
  → canonical ingest/backplane
  → Memory Fabric/Cortex/agent projections
```

`.14` is a web surface unless separately proven as an approved canonical runtime host. A browser login, a native Desktop session and a terminal session are distinct surfaces and must carry explicit topology metadata.

## Required topology binding

Every request/event carries:

```text
installation_id
device_id
login_surface_id
principal_id
tenant_id
session_id
conversation_id
```

The backplane is the single route for session continuity, event replay, memory projections, learning events and receipts. Local caches may accelerate reads but may not silently become writers.

## Acceptance criteria

- same principal/session semantics across `.14`, PC and laptop;
- no separate surface-owned durable memory writer;
- reconnect/replay is idempotent;
- surface projection exposes canonical authority and freshness;
- session and device isolation is read back;
- known-good Desktop remains an immutable rollback baseline during rollout.

## Explicit web migration gate

The existing web GUI remains the operational user-facing baseline while P1 broker/auth/session/thread parity is unresolved. Do **not** replace it with the Desktop front layer yet.

The Desktop front layer may be introduced only as:

```text
parallel shadow/canary surface
→ same canonical auth/session
→ same Hermes engine/backplane
→ thread/session parity readback
→ health and rollback proof
→ owner-approved cutover
```

A visual match is not sufficient. The migration is blocked until the web route, Desktop route and backend authority return the same scoped conversation/thread projection. The existing web surface and known-good Desktop are rollback baselines.

## Explicit non-goal

This CAD does not authorize changing the canonical production host, auth provider or existing Hermes Desktop baseline without a separate topology and authority gate.
