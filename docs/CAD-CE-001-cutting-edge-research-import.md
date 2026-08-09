# CAD-CE-001 — Cutting-edge research import and evaluation

**Parent:** `MWP-UOSH-001`  
**Status:** Source-verified candidates / evaluation pending  
**Import:** `docs/mwp-cutting-edge-research-import-v1.json`

## Architectural consequence

The ASI architecture should evaluate improvements along four dimensions:

```text
harness evolution
+ continual learning
+ calibrated world-model probing/correction
+ efficient layered planning
```

These are not automatically adopted. Each candidate enters as a shadow
experiment mapped to an existing CAD lane and must beat a baseline without
regression in safety, cost, latency or provenance.

## Required experiment classes

- **Memory-on/off longitudinal evaluation:** does retained experience improve
  future tasks, and through which save/retrieve/update path?
- **Distributed harness-evolution shadow:** can agents contribute proposals
  without centralizing raw private experience or granting self-authority?
- **World-model probe/correction:** does targeted environment probing or
  failure-amplifier repair improve outcomes versus longer reasoning alone?
- **Layered planning benchmark:** does symbolic/statistical/LLM fallback improve
  quality per cost and latency?

## Non-claims

A paper abstract or benchmark result is not proof that the pattern works in
our system. The import remains `PROPOSED` until local baselines, independent evaluation,
owner promotion decision and rollback receipts exist.
