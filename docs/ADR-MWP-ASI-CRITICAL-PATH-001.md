# ADR-MWP-ASI-CRITICAL-PATH-001 — Dependency order before breadth

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED / LIVE_ACCESS_READBACK`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `CAD-MWP-ASI-CRITICAL-PATH-001`

## Decision

MWP work follows the phase dependency order:

```text
auth/session → CRUD/truth → ingest/memory → learning → roundtrip → surfaces → writers → autonomy
```

This is not a claim that all work must be serial. Independent read-only discovery, tests, contracts, backup and reconciliation may continue in parallel. It is a rule against promoting dependent lanes before their prerequisites are live and evidenced.

## Rationale

- memory cannot be correctly scoped without principal/session/tenant authority;
- learning cannot be promoted safely without canonical CRUD and provenance;
- surfaces cannot be unified by frontend replacement while sessions diverge;
- graph/Obsidian writers cannot be made safe without canonical authority and rollback;
- ASI claims cannot rest on declared loops without measured runtime effect.

## Non-breaking rule

Hermes core and the known-good Desktop/session are rollback baselines. New web/front surfaces are introduced by compatibility/canary migration, never by destructive replacement or a second writer.

## Closeout rule

A phase closes only when its gate receipts are fresh and its predecessor phases are `COMPLETE` or explicitly accepted as `BLOCKED` with owner/evidence/next_action. A side-lane cannot advance the parent phase by being locally green alone.

## 2026-08-09 cross-surface access delta

The current metadata-only access readback is recorded in `docs/mwp-cross-surface-access-readback-v1.json`.

- MWP/Hermes Git trees are writable; a 102-artifact isolated allowlist exists, but commit/push requires the `.13` GitHub surface → runtime CLI handoff.
- Neo4j graph read is live-verified (`/neo4j/status` → connected); the orchestrator canary has write/rollback/read-after-delete evidence, but canonical writer audit authority remains unverified (`0` receipts).
- The live lateral-bus HTTP route currently returns `404`; source/runtime wiring remains open.
- The active Obsidian vault is `/Users/morpheus/Documents/Brain`; the metadata-only projection has been written and read back successfully.

This delta is an access/readback record, not a blanket promotion or authority grant.
