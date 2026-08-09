# ADR-H10-SEMANTIC-BOUNDARY-001 — Theory, evidence, capability and runtime truth

**Status:** ACCEPTED_SCHEMA / promotion gated  
**Owner:** Morten / theory and Opus architecture authority  
**Scope:** H10 Theory/Cosmos, EFC, EBE, RCMP, S0/S1, L0-L3, consciousness/meta, ASI OS/map and steward proposals

## Decision

H10 records must keep five distinct semantic layers. A record may reference several layers, but may not promote one layer into another without an explicit gate and provenance receipt.

```text
THEORY
  → ARCHITECTURE_INTENT
  → CAPABILITY_DECLARATION
  → RUNTIME_EVIDENCE
  → ROADMAP/PROPOSAL
```

These are not a maturity ladder. A theory does not become runtime merely because it is named in a registry; a capability declaration does not prove liveness; a roadmap item does not become an authority.

## Canonical status vocabulary

### Claim status

```text
THEORY_CLAIM          ontological/theoretical proposition
HYPOTHESIS            explicitly testable but not validated
PREDICTION            falsifiable forward-looking consequence
EVIDENCE_INTERNAL     evidence from the project/source package
EVIDENCE_EXTERNAL     independent external evidence
VALIDATION_PENDING    test/evaluation is defined but not closed
VALIDATED             evaluation receipt exists
FALSIFIED             evaluation rejected the claim
METHODOLOGY           method/protocol, not a truth claim
ONTOLOGY              vocabulary/structure, not empirical validation
UNCLASSIFIED          insufficient evidence; never promoted
```

### Record layer

```text
THEORY
ARCHITECTURE_INTENT
CAPABILITY_DECLARATION
LIVE_RUNTIME_EVIDENCE
ROADMAP_PROPOSAL
SUPPORTING_ARTIFACT
METHODOLOGY
PREDICTION_ARTIFACT
EVALUATION_ARTIFACT
```

### Runtime status

```text
NOT_APPLICABLE
DECLARED_ONLY
PROPOSED_NOT_LIVE
LIVE_UNVERIFIED
LIVE_VERIFIED
STALE
RETIRED
```

## Invariants

1. `claim_status` and `record_layer` are separate fields.
2. `LIVE_VERIFIED` requires an independent runtime receipt; source text, README, registry or UI is insufficient.
3. `VALIDATED` requires a reproducible evaluation receipt and provenance; it does not imply runtime capability.
4. `UNCLASSIFIED` and ambiguous records are quarantined from graph projection and steward authority.
5. Every promotion carries `source_ref`, `source_version`, `reviewer/owner`, `evaluated_at`, `provenance_ref` and `rollback_ref` where consequential.
6. A proposed steward has no authority merely because a record references it.
7. Theory, evidence, hypothesis and prediction must never be collapsed into one graph status.
8. Supersession creates a new version/event; it does not overwrite historical claim truth.

## Required TheoryHomeRecord fields

```text
record_id
package_id
home_class
lane_id
record_layer
claim_status
runtime_status
source_ref
source_version
provenance_ref
owner_id
review_status
freshness
rollback_ref (when promoted)
```

## Fail-closed promotion

```text
missing semantic fields       → UNCLASSIFIED
ambiguous layer/status        → BLOCKED_SEMANTIC_CLASSIFICATION
runtime claim without receipt → BLOCKED_RUNTIME_AUTHORITY
validated claim without eval  → VALIDATION_PENDING
```

No H10 graph write, public publication, ASI-map promotion or steward activation may rely on heuristic keyword classification alone.
