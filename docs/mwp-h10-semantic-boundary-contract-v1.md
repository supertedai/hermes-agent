# MWP-H10 semantic boundary contract v1

## Gate

Every TheoryHomeRecord must be classified independently on:

```text
record_layer
claim_status
runtime_status
```

## Allowed promotion

```text
THEORY_CLAIM + THEORETICAL record → no runtime authority
HYPOTHESIS/PREDICTION → VALIDATION_PENDING until evaluation receipt
VALIDATED → requires evaluation/provenance receipt
CAPABILITY_DECLARATION → DECLARED_ONLY until runtime receipt
LIVE_RUNTIME_EVIDENCE → LIVE_VERIFIED only with independent liveness/authority
ROADMAP_PROPOSAL → proposal only; never graph/runtime authority
SUPPORTING_ARTIFACT → data/figure/toolkit/package support; never a claim or runtime authority
METHODOLOGY → method/protocol artifact; may contain predictions but is not validated evidence by itself
PREDICTION_ARTIFACT → sealed/falsifiable prediction package; requires evaluation receipt
EVALUATION_ARTIFACT → empirical validation/observational pipeline package; does not prove a claim without evaluation evidence
UNCLASSIFIED → quarantined
```

## Required evidence

```text
source_ref
source_version
provenance_ref
owner_id
review_status
freshness
rollback_ref where promoted
```

## MWP gate behavior

- heuristic keyword matches may propose a classification but cannot promote it;
- ambiguous or missing values become `BLOCKED_SEMANTIC_CLASSIFICATION`;
- graph projection, publication, ASI-map promotion and steward activation require semantic classification first;
- all changes use metadata-only receipts and preserve supersession/history.
