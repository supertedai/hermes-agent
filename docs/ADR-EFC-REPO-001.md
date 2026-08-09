# ADR-EFC-REPO-001 — EFC repository closeout requires cross-surface receipts

**Status:** Proposed / owner review required  
**Parent:** `MWP-UOSH-001`

## Decision

EFC repository status is reported in separate dimensions:

```text
source_integrity
public_publish
workflow_liveness
scientific_evaluation
provenance/governance
runtime_projection
```

No single green GitHub Pages deployment may close the repository or EFC
programme. Public pages, GitHub Actions, DOI ledger, graph, Cortex and runtime
must each have their own receipt.

## Rules

1. A failing active verify workflow is a blocker, not noise.
2. A manually disabled workflow must be classified before it is considered
   healthy.
3. README/AGENTS/layer/llms/public counts must come from one canonical source.
4. Public validation results must retain evidence-layer labels when projected
   into graph/world model.
5. Model comparison is not complete until identical dataset, likelihood,
   nuisance parameters and reference model are executed.
6. EFC-derived meta-model or ASI-OS signals remain proposal/derived metadata
   until baseline, ablation and independent evaluation pass.

## Non-goals

This ADR does not change EFC source, re-enable workflows, alter sealed
predictions or write graph/runtime state. Those are separate owner-gated BLs.
