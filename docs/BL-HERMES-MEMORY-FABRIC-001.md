# BL-HERMES-MEMORY-FABRIC-001 — Hermes-centred memory roundtrip

**Status:** `PARTIAL / CANARY_COMPLETE_PRODUCTION_GATES_OPEN`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-MEMORY-FABRIC-001 → ADR-HERMES-MEMORY-FABRIC-001`
**Mutation policy:** metadata-only until authority and rollback are verified

## Gates

| Gate | Requirement | Initial status |
|---|---|---|
| G1 | Inventory all memory layers with datatype, store, owner and scope | `PARTIAL` |
| G2 | Prove Hermes engine is the runtime path for chat, Cortex and agents | `UNVERIFIED` |
| G3 | Bind MemoryProvider/Holographic semantics to canonical Memory Fabric | `UNVERIFIED` |
| G4 | Verify Chat → Cortex and Chat → Agent scoped roundtrips | `UNVERIFIED` |
| G5 | Verify Agent → Cortex and Cortex → Agent handoffs | `UNVERIFIED` |
| G6 | Verify provenance, freshness, conflict, correction and tombstone behavior | `OPEN` |
| G7 | Verify canonical writes, idempotency, read-after-write and rollback | `BLOCKED_UNTIL_AUTHORITY` |
| G8 | Verify Hermes-visible and runtime-effective context use | `UNVERIFIED` |
| G9 | Verify degraded/read-only behavior and cache invalidation | `OPEN` |
| G10 | Verify learning promotion: retrieved → used → measured → promoted/rolled back | `PARTIAL` |
| G11 | Verify graph/vector/GNN projections against canonical state | `BLOCKED` |
| G12 | Verify multi-user, tenant, device, session and agent isolation | `BLOCKED_UNTIL_LIVE_READBACK` |

## Required receipt fields

```text
receipt_id
canonical_authority_ref
principal_id
tenant_id
system_scope
conversation_id
session_id
agent_id
cortex_ref
memory_layer_id
entity_version
content_hash
projection_state
provenance_ref
freshness_seconds
runtime_effect_ref
rollback_ref
status
```

Receipts are metadata-only and must not contain raw prompts, private memory payloads, credentials or sensitive content.

## Closeout rule

This BL remains `OPEN` until all required gates are `COMPLETE`, or explicitly `BLOCKED` with owner, evidence and next action. Parent MWP closeout is prohibited while any required gate is unresolved.

## 2026-08-10 layer-inventory delta (Symbiose ADR-061 step 1 / BL-4007)

A read-only per-principal measurement of the 20-layer Symbiose user-memory contract is live:
`tools/user_memory_layers.measure(<uid>)` on `.12`, exposed as `GET /api/v1/memory/layers` and
mirrored to `.15` as `<home>/symbiose/selfstate.json`. Every row carries key, state and count
with an explicit honesty vocabulary (`measured` / `pending_link` / `blind` / `absent` /
`unreachable` / `no_principal`); `unreachable` is never rendered as `0`, `absent` never as
empty, and `pending_link` always carries both linked and substrate counts.

G1 moves `OPEN → PARTIAL`, deliberately not `COMPLETE`:

- the inventory covers the USER plane only. The Hermes chat/session, Cortex/system and
  agent/steward planes are not enumerated by the same reader;
- Hindsight is declared explicitly OUTSIDE the 20-layer contract, so it is neither `measured`
  nor `absent` here — a store the register does not know would make the register's claim to
  completeness untrue, so it is named rather than silently omitted.

Partial progress on the required receipt fields: `entity_version` and `content_hash` now travel
with the mirrored projection (content hash is taken over the MEASURED body only, excluding
timestamps, so an unchanged body keeps a stable hash). `projection_state`, `receipt_id`,
`canonical_authority_ref`, `provenance_ref`, `runtime_effect_ref` and `rollback_ref` are still
absent.

**This work is UNDER the Hindsight-addendum acceptance bar and does not approach it.**
No shadow receipt is produced: no provider/config identity, no candidate/recall identifiers,
no latency measurement, no evaluation against the local SQLite/FTS5 baseline, no rollback path
expressed in data. ADR-061 §10 already records that step 0 lands under this bar; step 1 inherits
the same deficit and, having only a verification in a commit message rather than a stated proof,
is further from it. G2-G12 are untouched.
