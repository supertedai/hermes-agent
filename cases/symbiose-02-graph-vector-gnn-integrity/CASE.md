# MWP-UOSH-001 / CASE-SYMBIOSE-02 — Graph/Qdrant/GNN integrity and provenance

## Purpose

Reconcile and repair the live Symbiose knowledge path without creating a second authority:

```text
canonical source/provenance
  → Neo4j graph
  → Qdrant vector index
  → GNN similarity/promotion
  → agent/runtime readback
```

The case covers the findings from the live 2026-08-06 probe: graph and Qdrant are reachable and fast; graph content contains duplicate/deprecated/provenance ambiguity; GNN is reachable but reports embedding collapse and degraded semantic quality.

## Scope

### In scope

- graph canonical IDs, duplicate detection and merge/quarantine plan;
- relation-type normalization (`Supports` versus `SUPPORTS` and equivalent drift);
- active versus deprecated concept separation;
- source, owner, freshness, confidence and provenance readback;
- deterministic graph-to-Qdrant export and shadow reindex;
- Qdrant retrieval-quality evaluation against a versioned query/evidence set;
- GNN collapse diagnosis, baseline comparison, shadow repair/retraining or rollback;
- agent/runtime metadata readback for stale, stopped, unknown and healthy workers;
- end-to-end gates, rollback and metadata-only reporting.

### Out of scope until separately gated

- deleting or merging live graph records;
- promoting a new Qdrant collection;
- retraining/promoting a GNN checkpoint;
- activating, restarting or repairing daemons;
- changing writers, schedulers, credentials or user-private payload policy;
- minting a new BL/ADR/CAD identifier.

## Hard dependencies

- `CASE-AUTONOMY-00`: MWP IDs, axis/scope, dependency and evidence contract.
- `CASE-IDENTITY-01`: principal/session authority and owner gate.
- Kanban/task authority: canonical durable task/case state.
- Evidence/provenance ledger: metadata-only evidence references and read-after-write contract.
- Existing Symbiose unified API on `.12:8010`.
- Existing Neo4j graph on `.12:7474/.7687`.
- Existing Qdrant on `.12:6333`.
- Existing GNN route `/gnn/similar/{concept}` and its serving/collapse diagnostics.
- A versioned evaluation set with canonical concepts, expected neighbors and negative cases.
- A tested rollback target for graph snapshot, Qdrant collection/index and GNN checkpoint.

## Current live evidence (read-only)

- Unified API health: HTTP `200`; `loop_lag_s=0.002`; `budget_s=5.0`.
- Graph query for `Homo Fluxus`: HTTP `200`; a small query measured approximately `762 ms`.
- Graph returned multiple labels for the same concept, including active and `DeprecatedConcept` variants.
- Live graph relationships include `Supports`, `DERIVES_FROM`, `IS_A`, `DEFINITION` and `ABBREVIATION_OF` between EFC/Energy-Flow Cosmology and Homo Fluxus.
- Qdrant root: HTTP `200`; version `1.18.3`; measured approximately `2.0 ms`.
- Qdrant collection listing: HTTP `200`; measured approximately `1.8 ms`.
- GNN route for `Homo Fluxus` and `EFC`: HTTP `200`, but `degraded=true`; mean pairwise cosine `0.867` exceeds collapse threshold `0.85`.
- Fleet metadata route: HTTP `200`; `362` workers/daemons, including healthy, stopped, unknown and stale entries; this is a runtime readback, not proof that every worker is currently live.

## Dependency DAG

```text
CASE-AUTONOMY-00
  └── CASE-IDENTITY-01
        └── canonical task/evidence authority
              └── SYMBIOSE-02A graph/provenance audit
                    ├── SYMBIOSE-02B canonical graph shadow repair
                    │     └── SYMBIOSE-02C Qdrant shadow reindex + retrieval eval
                    └── SYMBIOSE-02D GNN collapse diagnosis/baseline
                          └── SYMBIOSE-02E GNN shadow repair/eval
                                └── SYMBIOSE-02F promotion and runtime readback
```

No child may be promoted while its predecessor is blocked, stale, owner-gated or missing evidence.

## Work packages

### SYMBIOSE-02A — Graph/provenance audit

Produce metadata-only inventories for canonical IDs, duplicate clusters, relation casing, deprecated nodes, source refs, owners, freshness, confidence and writer lineage. Classify each finding as `EXISTS_BUT_UNVERIFIED`, `EXISTS_BUT_STALE`, `EXISTS_BUT_CONFLICTING`, `EXISTS_BUT_WRONG_SCOPE` or `MISSING`.

### SYMBIOSE-02B — Canonical graph shadow repair

Design and execute only in an isolated/shadow representation first. Preserve historical nodes and provenance; do not destructive-merge without an owner-approved rollback plan. Validate uniqueness, relation normalization and active/deprecated separation.

### SYMBIOSE-02C — Qdrant shadow reindex and retrieval evaluation

Export from the canonical shadow graph, re-embed deterministically, build a shadow collection, and compare against the current index. Measure precision@k, recall@k, duplicate rate, stale-hit rate, provenance completeness and latency. Promote only after the evaluation gate is green.

### SYMBIOSE-02D — GNN collapse diagnosis/baseline

Identify whether collapse is caused by training data, tier routing, normalization, checkpoint, propagation, negative sampling or deployment. Compare against a simple graph/vector baseline. Add a hard collapse gate using pairwise cosine and per-dimension variance.

### SYMBIOSE-02E — GNN shadow repair/evaluation

Repair, retrain or roll back in shadow. Evaluate concept neighborhoods, cross-domain separation, duplicate sensitivity, deprecated-node suppression and calibration. A responding endpoint is insufficient; semantic quality must beat the baseline.

### SYMBIOSE-02F — Promotion and runtime readback

Only after owner/security/evidence gates: promote graph/index/model artifacts, verify read-after-write, confirm rollback handles, inspect fleet status and report healthy/stale/stopped/unknown separately. No parent closeout before all child coverage is green or explicitly blocked with an owner and next gate.

## Gates

- **Identity gate:** principal, session, profile and axis resolved.
- **Authority gate:** MWP/Kanban remains the canonical task authority.
- **Read-only discovery gate:** no mutation during audit.
- **Provenance gate:** every promoted item has source, writer, timestamp, freshness and evidence refs.
- **Canonicalization gate:** duplicate and deprecated handling is deterministic and reversible.
- **Retrieval gate:** Qdrant shadow improves or preserves measured quality against baseline.
- **Collapse gate:** GNN fails closed when embedding variance/cosine thresholds are violated.
- **Runtime gate:** service health, latency, liveness and role are read back from the intended target.
- **Rollback gate:** graph, vector index and GNN checkpoint each have an independently verifiable rollback ref.
- **Owner gate:** any live merge, promotion, restart or writer change requires explicit owner approval.

## Acceptance criteria

- No duplicate canonical concept is promoted without a merge/quarantine decision and provenance.
- Relation names are normalized while original history remains auditable.
- Deprecated concepts cannot silently outrank active concepts.
- Qdrant retrieval is evaluated with a versioned test set; HTTP health alone is not accepted.
- GNN collapse is detected automatically and prevents promotion.
- Graph, Qdrant, GNN and agent status are reported as separate runtime layers.
- Every result has status, target, latency, freshness, provenance, confidence, gate, evidence ref and next permitted action.
- All mutation paths have a dry-run, shadow diff, owner gate and rollback reference.
- Parent MWP case remains open until all coverage is green or explicitly blocked.

## Status

`SYMBIOSE-02A AUDIT COMPLETE / SHADOW REPAIR AND PROMOTION BLOCKED`

The metadata-only graph/provenance audit has a receipt at
`docs/mwp-symbiose-02a-audit-receipt.json`. It confirms reachability and exposes
identity/provenance drift, but it does not authorize graph mutation, Qdrant
reindexing, GNN repair/promotion or daemon changes.

The first decision-set artifact is
`docs/mwp-symbiose-canonicalization-decisions-v1.json`
(relative to the isolated MWP worktree). The redacted node-level shadow readback found 6 active and 6 deprecated rows,
source on 2 rows, freshness on 3 rows, and no owner or confidence fields. The six
deprecated rows are provisional shadow `quarantine` candidates; the six active rows
remain `unresolved`. No row is retain- or merge-ready.

## Next permitted action

The rollback-discovery receipt is
`docs/mwp-symbiose-rollback-discovery-receipt-v1.json`. Graph snapshot, Qdrant
snapshot/backup and GNN checkpoint handles are not independently verified, so the
rollback gate is `BLOCKED`; no promotion is permitted.

The labeled retrieval schema and shadow receipt are
`docs/mwp-symbiose-labeled-retrieval-v1.json` and
`docs/mwp-symbiose-labeled-retrieval-shadow-receipt-v1.json`. Both query classes
return five chunks, while stable chunk identity is not exposed; precision/recall
cannot be measured honestly yet.

## Next permitted action

Obtain owner labels and expose stable chunk identity/provenance metadata in the
read-only retrieval route. Rollback, owner and promotion gates remain blocked.
