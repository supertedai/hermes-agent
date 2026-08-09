# MWP-UOSH-001 — SYMBIOSE-02 shadow canonicalization plan

**Parent:** `CASE-SYMBIOSE-02`
**Depends on:** `SYMBIOSE-02A` audit receipt
**Mode:** design/read-only; no live mutation
**Status:** REVIEW_REQUIRED / NOT AUTHORIZED FOR EXECUTION

## Objective

Create a reversible shadow representation that can measure graph canonicalization,
Qdrant retrieval quality and GNN collapse independently before any live promotion.

## Shadow stages

1. **Graph inventory freeze**
   - Export only metadata: canonical candidate ID, labels, relation types, source,
     owner, freshness, confidence and writer lineage.
   - Preserve the source node identifier and historical labels.
   - Hash the inventory and record the query/evidence reference.

2. **Deterministic canonicalization proposal**
   - Group duplicate candidates by an explicit, versioned key.
   - Normalize relation casing in shadow output only.
   - Keep active and deprecated concepts separate.
   - Emit `merge`, `quarantine` or `retain` decisions with reason and confidence.
   - No live graph writes.

3. **Qdrant retrieval baseline**
   - Use a versioned query/evidence set with positive and negative cases.
   - Measure precision@k, recall@k, duplicate-hit rate, stale-hit rate,
     provenance completeness and latency.
   - Compare shadow output against the current collection before promotion.

4. **GNN collapse baseline**
   - Record mean pairwise cosine, per-dimension variance and neighborhood overlap.
   - The observed `degraded=true` state remains a hard promotion block.
   - Compare against a simple graph/vector baseline before any repair proposal.

## Required gates

- **Owner:** explicit owner/reviewer decision for any live mutation.
- **Authority:** MWP task state must resolve through existing Kanban; no second store.
- **Identity:** installation, login surface, principal and agent scope resolved.
- **Provenance:** every shadow row has source, writer, timestamp/freshness and evidence ref.
- **Evaluation:** versioned retrieval and GNN metrics exist before comparison.
- **Rollback:** graph snapshot, Qdrant collection/index and GNN checkpoint handles exist.
- **Promotion:** only after all predecessor gates are green and read-after-write is verified.

## Explicit blockers

```text
Kanban operational board: 0 tasks / not instantiated for MWP
Active Desktop session identity: not verified
Role/provider runtime binding: unverified
GNN: degraded=true
Obsidian canonical vault: unverified
Live graph/Qdrant/GNN writes: not authorized
```

## Permitted next action

Run the inventory and metric collection in an isolated/shadow output only, after a
reviewer accepts the query/evidence-set definition. Until then this document is a
plan artifact, not an execution authorization.

## Rollback

Delete the shadow artifact and its receipt. No live destination rollback is needed
because this plan authorizes no live write.
