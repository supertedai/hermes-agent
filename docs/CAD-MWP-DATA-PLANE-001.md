# CAD-MWP-DATA-PLANE-001 — Governed schema, graph, Qdrant and GNN foundation

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED`
**Parent:** `MWP-UOSH-001`
**Phase:** `P7`, dependency `P2 canonical CRUD/truth/authority`

## Decision

Schema, graph, Qdrant and GNN are treated as one governed data plane behind the Hermes/Memory Fabric architecture. They are not independent sources of truth.

```text
canonical entity/event schema
        ↓
canonical authority + event log
        ├── Neo4j graph projection
        ├── Qdrant vector projection
        ├── GNN feature/training projection
        └── Hermes context/retrieval projection
```

The data plane must be schema-first, versioned, tenant/scope-aware, provenance-bearing, rebuildable and measurable before production promotion.

## Schema-first requirements

Every entity/event type has:

```text
schema_id
schema_version
owner
canonical_authority
scope/tenant policy
identity key
content hash
provenance fields
lifecycle/tombstone policy
migration + rollback
projection mapping
compatibility policy
```

No store-specific payload may silently define a new canonical field or identity.

## Graph requirements

Neo4j/graph projections require:

- explicit node/edge labels and constraints;
- stable canonical IDs and uniqueness constraints;
- tenant/principal/system-scope boundaries;
- provenance, source, version and evidence references;
- temporal validity and supersession where relevant;
- migration up/down/validate artifacts;
- projection rebuild from canonical events;
- query plan/index health and authorization tests;
- snapshot/restore and read-after-restore proof.

## Qdrant requirements

Every collection declares:

```text
collection_id
schema_id/version
embedding_model_ref + dimension
distance metric
point/chunk identity
canonical entity/event ref
tenant/scope filters
payload indexes
HNSW/quantization policy
freshness/deletion policy
replication/shard policy
snapshot/restore reference
```

Vector similarity is retrieval evidence, not truth. Qdrant must never bypass canonical scope or promote facts by score alone.

## GNN requirements

Every GNN model/dataset declares:

```text
model_id/version
checkpoint hash
feature schema/version
label/edge schema
training/evaluation split
leakage controls
baseline and metrics
calibration/uncertainty
serving route
drift monitor
checkpoint restore
rollback reference
```

GNN output is a ranked/derived signal. It cannot become canonical truth without provenance and promotion gates.

## Quality and conformance

Required evaluations include:

```text
schema compatibility
cross-store identity parity
scope leakage tests
graph/vector projection parity
precision@k / recall@k
MRR/nDCG where applicable
stale-hit and duplicate rate
conflict/contradiction rate
GNN baseline comparison
calibration and drift
restore/rebuild conformance
```

## Non-goals

This CAD does not authorize mass migration, collection deletion, graph writes, vector rewrites or GNN retraining. Those require P2 authority, bounded change-gates and rollback receipts.
