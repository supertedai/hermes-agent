# MWP-UOSH — cross-surface truth and CRUD gate

**Contract:** ADR-TRUTH-001
**Status:** CONTRACT_BUILT / LIVE_AUTHORITY_GATED

## Required mutation envelope

Every create/update/delete must carry:

```text
mutation_id
idempotency_key
operation
canonical_key = tenant_id + system_scope + entity_type + entity_id
principal_id
auth_context_ref
canonical_authority_ref
source_surface
expected_version
provenance_ref
occurred_at
```

## Required receipts

```text
canonical_write_receipt
outbox_event_receipt
canonical_read_after_write
projection_receipts[]
rollback_ref (when consequential)
```

Each receipt is metadata-only and must include:

```text
mutation_id
canonical_key
entity_version
content_hash
projection_state
principal_id
tenant_id
system_scope
provenance_ref
readback_at
```

## Gate states

```text
COMPLETE          canonical + outbox + readback + required projections agree
PENDING_READBACK  write claimed but canonical/projection readback missing
STALE             projection version behind canonical
DIVERGED          version/hash/authority differs
CONFLICT          expected_version rejected
BLOCKED           authority/scope/rollback/outbox gate missing
UNKNOWN           evidence insufficient
```

## MWP enforcement

- Chat, Desktop and web/API are clients, not authorities.
- Kanban `.15` is authoritative for its canonical board; `.12` is a local projection unless explicitly promoted by authority evidence.
- Agent/steward registry, capability, liveness and provider declarations are separate from live runtime truth.
- Graph, Qdrant, GNN, memory and UI projections require source/version/hash/provenance readback.
- No child-task, agent routing, memory promotion, graph merge or Faber execution may rely on a `STALE`, `DIVERGED`, `UNKNOWN` or `UNVERIFIED` surface.
- A failed read-after-write leaves the mutation open/blocked; it is never reported as complete.

## Reconciliation

```text
1. identify canonical authority
2. compare canonical key, version and hash
3. classify surface: FRESH/STALE/DIVERGED/UNKNOWN
4. stop routing and promotion on conflict
5. create owner-scoped repair proposal
6. require evaluation, rollback and read-after-write
7. promote only after all required receipts agree
```

## Continuous MWP/CAD/ADR/BL destination synchronization

The following is the canonical projection rule:

```text
source artifact / authority
→ canonical identity + version + content_hash
→ typed projection plan
→ destination write through the destination writer
→ destination read-after-write
→ projection receipt
→ freshness/drift monitor
```

The surfaces are not flattened copies:

| Surface | Role | Projection shape | Required gate |
|---|---|---|---|
| Git/GitHub | canonical source package for versioned MWP/CAD/ADR/BL artifacts | files, history, branch/commit refs | scoped diff, commit, remote readback |
| Obsidian | human-curated knowledge projection | MOC/notes/links, no raw runtime secrets | vault target, note pre-read, hash/readback |
| Graph | structured authority/projection | entities, relationships, provenance | graph target pre-read, writer grant, receipt/readback |
| Runtime | execution/session/authority truth | metadata-only receipts | live principal, scope, health, provenance |

### Freshness and drift

Every projection has:

```text
canonical_version
canonical_hash
projected_version
projected_hash
last_successful_readback
freshness_deadline
projection_status
repair_ref
```

A scheduled/read-on-demand reconciler must classify each projection as:

```text
FRESH
STALE
DIVERGED
CONFLICT
UNKNOWN
BLOCKED
```

It must stop promotion, routing and further writes for `STALE`, `DIVERGED`, `CONFLICT`, `UNKNOWN` or `BLOCKED` unless an owner-approved repair gate exists.

### CAD/ADR/BL mapping

Every relevant CAD, ADR and BL receives a mapping record:

```text
source_id
source_path_or_remote_ref
mwp_id
case_id
parent_task_id
child_task_id
owner
authority
canonical_version
projection_targets[]
source_hash
projection_receipts[]
rollback_ref
status
```

No record is considered "synced everywhere" merely because it exists in one surface. `COMPLETE` requires all required destination receipts for that record.

### Operational requirement

The sync loop must be single-writer/idempotent per canonical key, emit metadata-only receipts, reconcile at a defined cadence and on every destination write, and create an owner-scoped repair proposal instead of silently overwriting divergence.

Current implementation status:

```text
contract:                 BUILT
Morten bounded receipts:  VERIFIED
Git scoped package:       PUSHED
Obsidian MWP projection:  VERIFIED
Graph bounded relation:   VERIFIED
full CAD/ADR/BL sync loop: NOT_YET_IMPLEMENTED
continuous runtime monitor: NOT_YET_VERIFIED
```

## Current MWP implication

The `.12` versus `.15` Kanban discrepancy remains a concrete instance of `AUTHORITY_SPLIT / PENDING_CANONICAL_RECONCILIATION`, not a harmless replica difference. The canonical `.15` parent repair was accepted only after `.15` write return and `.15` read-after-write verification; child/lease remains gated.
