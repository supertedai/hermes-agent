# ADR-RECURSIVE-IMPROVEMENT-001 — Web-informed bounded improvement scout

**Status:** Proposed / owner review required  
**Date:** 2026-08-07  
**Decision scope:** MWP-UOSH-001, ASI/CAD recursive-improvement lane

## Context

The system benefits from external inspiration, but unrestricted web-driven
self-modification would mix untrusted claims, code, skills, authority and
runtime state. Recursive improvement must therefore be treated as a governed
proposal/evaluation loop, not as autonomous self-editing.

The current architecture is internally coherent, but it has an external-horizon
gap: improvement discovery has been driven mainly by internal observations and
sporadic external inputs. The scout exists to correct this internal
over-optimization risk through continuous horizon scanning, adversarial
comparison and transfer analysis.

## Decision

Create one dedicated proposal-only agent:

```text
agent_id: recursive-improvement-scout
```

It may search the web and internal sources, compare patterns against the MWP
gap register, and produce bounded improvement proposals. It must use existing
MWP task authority, evidence references, worktree isolation, evaluation and
rollback contracts.

## Mandatory gates

1. **Source gate:** URL/repository/paper, retrieval timestamp, license/status,
   source quality and contradiction notes.
2. **Relevance gate:** explicit mapping to an existing gap, CAD lane, ADR and BL.
3. **Safety gate:** no secrets, prompt injection, untrusted executable payload or
   authority-changing instruction is imported.
4. **Experiment gate:** baseline, isolated worktree/sandbox, bounded budget and
   reproducible test command.
5. **Evaluation gate:** independent evaluator, regression checks, cost/latency
   impact and calibration/quality comparison.
6. **Promotion gate:** owner/reviewer decision, target pre-read, write receipt,
   read-after-write and rollback reference.
7. **Outcome gate:** post-promotion measurement and discard/rollback if benefit
   is not demonstrated.

## Rejected alternatives

- unrestricted self-modifying agent;
- automatic installation of community skills;
- web content as runtime authority;
- scout-owned scheduler or task database;
- self-approval of its own proposals.

## Consequences

Positive: broader discovery, reusable improvement proposals, explicit evidence
and lower risk of importing attractive but incompatible patterns.

Negative: promotion is slower than blind automation and requires evaluation and
owner gates.
