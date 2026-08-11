# CASE-AUTONOMY-00 — Model-role autonomy workflow

## Role separation

The autonomy workflow uses separate model roles. A model must not silently design, build and approve its own work.

```text
GPT Sol / design role
  → architecture, decomposition, acceptance criteria, risks, test plan

GPT Luna / build role
  → bounded implementation in isolated worktree, tests, evidence collection

GPT Sol or Claude / review role
  → independent review, diff/contract/security/readback verdict

Second opinion role
  → triggered by high blast radius, disagreement, uncertainty, failed review,
    new architecture choice or owner-gated decision
```

## Existing Hermes rails to reuse

- `PreflightGate`
- `GoalLedger`
- `FaberGoalRegistry`
- `ReviewVerdict`
- `ReviewEvidence`
- `LandingEvidence`
- `DefinitionOfDone`
- `StepJournal`
- Kanban model/workers/claims/leases
- verification evidence ledger

## State flow

```text
DESIGN
→ DESIGN_REVIEW
→ APPROVED_TO_BUILD
→ BUILD
→ VERIFY
→ INDEPENDENT_REVIEW
→ SECOND_OPINION (conditional)
→ OWNER_GATE (conditional)
→ LAND
→ MEASURE
→ LEARN
```

## Separation rules

- Design output is an immutable input to build; the builder cannot rewrite acceptance criteria silently.
- Build output includes diff, tests, readback and rollback evidence.
- Reviewer must inspect the actual diff/evidence, not only builder summary.
- Reviewer cannot approve its own design/build output without an independent second opinion.
- A disagreement becomes `CONFLICT`/`OWNER_GATE`, not an automatic pass.
- Model success/confidence is never a substitute for evidence or reviewer PASS.

## Model routing

Role-to-model/provider mapping must be resolved from live config/catalog at run time and recorded in evidence:

```text
role
model
provider
resolver_status
fallback
latency
cost (if available)
```

The labels `Sol`, `Luna` and `Claude` are workflow roles/aliases until live model resolver evidence proves their exact model/provider bindings.

## Second-opinion triggers

Trigger an independent second opinion when:

- blast radius is R3/R4/R5;
- identity, scope, writer or authority is ambiguous;
- CAD/ADR/BL mapping is new or conflicting;
- Sol and Luna disagree;
- reviewer verdict is BLOCK/ESCALATE;
- tests pass but runtime/readback is missing;
- graph/Qdrant/memory promotion is proposed;
- production/update/irreversible action is proposed.

## Acceptance

No task reaches `LANDED`/`CLOSED` without independent review evidence, and no task reaches `LEARNED` without measured effect evidence. Owner gates remain outside model authority under bounded autonomy.

## Status

`WORKFLOW DEFINED / RUNTIME ROLE MAPPING OPEN`
