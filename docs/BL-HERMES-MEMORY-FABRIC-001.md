# BL-HERMES-MEMORY-FABRIC-001 — Hermes-centred memory roundtrip

**Status:** `PARTIAL / CANARY_COMPLETE_PRODUCTION_GATES_OPEN`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-MEMORY-FABRIC-001 → ADR-HERMES-MEMORY-FABRIC-001`
**Mutation policy:** metadata-only until authority and rollback are verified

## Gates

| Gate | Requirement | Initial status |
|---|---|---|
| G1 | Inventory all memory layers with datatype, store, owner and scope | `OPEN` |
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
