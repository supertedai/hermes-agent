# ADR-TRUTH-001 — Cross-surface canonical truth for CRUD and updates

**Status:** ACCEPTED_ARCHITECTURE / runtime rollout gated  
**Owner:** MWP-UOSH authority  
**Scope:** Chat, Desktop, web/API, Kanban, agents/stewards, Cortex, memory, graph/Qdrant/GNN, projections and external integrations

## Decision

Every mutable entity has exactly one **canonical authority** for its tenant, scope and entity key. Other surfaces are projections or clients; they are never independent writers of the same entity.

```text
client surface
  → authenticated mutation envelope
  → canonical authority transaction
  → canonical version + content hash
  → transactional outbox/change event
  → projection fan-out
  → per-surface read-after-write receipt
  → convergence/reconciliation
```

## Invariants

1. **Canonical key:** `(tenant_id, system_scope, entity_type, entity_id)` identifies the entity. No surface may silently rewrite the key.
2. **Single writer:** CRUD and state-changing operations execute only through the canonical authority for that key.
3. **Idempotency:** every mutation has an idempotency key. Retries return the original mutation result; they do not create a second entity/event.
4. **Optimistic concurrency:** updates carry `expected_version`; stale writers are rejected, never merged implicitly.
5. **Monotonic truth:** canonical `entity_version` increases exactly once per committed mutation. A projection may never advertise a version greater than canonical.
6. **Hash binding:** canonical content hash is calculated over the redacted canonical representation. Surface receipts must reference the same hash for the same version.
7. **Transactional outbox:** canonical commit and change-event creation are one transaction. A committed mutation without an outbox event is invalid.
8. **Read-after-write:** a mutation is not `COMPLETE` until canonical readback verifies version, hash, authority, provenance and receipt status.
9. **Projection states:** `FRESH`, `STALE`, `DIVERGED` and `UNKNOWN` are explicit. Only `FRESH` may be shown as synchronized.
10. **Fail closed:** conflict, missing receipt, version regression, hash mismatch, unknown authority or stale provenance blocks promotion/routing.
11. **Delete truth:** deletion is a canonical tombstone/versioned event first. Hard deletion requires a separate retention/legal gate.
12. **Scope:** tenant, principal, consent, device/session and system-scope boundaries are carried through every mutation and receipt.
13. **Metadata-only receipts:** receipts contain identifiers, versions, hashes, status, timestamps, provenance refs and rollback refs — never raw prompts, private memory, credentials or sensitive payloads.
14. **No repair by blind overwrite:** reconciliation proposes a bounded repair; it does not overwrite canonical truth without owner/policy/evaluation/rollback gates.

## CRUD protocol

| Operation | Required gate |
|---|---|
| Create | canonical authority, idempotency, scope, provenance, version `1`, outbox, readback |
| Read | scope/authorization, canonical or explicitly labelled projection freshness |
| Update | expected version, canonical write, monotonic version, outbox, readback |
| Delete | canonical tombstone, retention/policy gate, outbox, readback |
| Retry | same idempotency key and mutation result |
| Reconcile | compare version/hash first; owner/evaluation/rollback before repair |

## Surface contract

Each surface reports:

```text
canonical_authority_ref
canonical_key
entity_version
content_hash
projection_state
mutation_id
idempotency_key
principal_id
tenant_id
system_scope
provenance_ref
readback_at
rollback_ref
```

A surface that cannot provide this is `UNKNOWN`, not synchronized.

## Failure handling

- canonical unavailable → no local write; return `BLOCKED_CANONICAL_UNAVAILABLE`;
- stale expected version → `CONFLICT_EXPECTED_VERSION`;
- hash mismatch → `DIVERGED_HASH`;
- missing/late outbox → `BLOCKED_OUTBOX`;
- missing surface readback → `PENDING_READBACK`;
- two canonical authorities → `BLOCKED_AUTHORITY_SPLIT`.

## Consequences

This prevents the `.12`/`.15` Kanban split from being interpreted as one truth: each authority must be named, and convergence must be proven by canonical readback. It also prevents UI-reported memory, agent registry entries or cached model/provider declarations from being treated as live authority.

## Promotion gate

`LIVE_VERIFIED` requires:

```text
canonical write receipt
+ outbox/change-event receipt
+ canonical read-after-write
+ every required projection receipt
+ version/hash equality
+ provenance/scope/owner
+ rollback reference where consequential
```

Otherwise the state remains `OPEN`, `BLOCKED`, `STALE`, `DIVERGED` or `UNVERIFIED`.
