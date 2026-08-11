# CASE-AUTONOMY-00 — Existing autonomy workflow and skill mapping

## Executive verdict

The canonical 13-step workflow exists as the active Hermes skill:

```text
~/.hermes/skills/software-engineering/autocoder-13-step-workflow/SKILL.md
```

It is normative and must be reused. It explicitly defines Sol design/review, Faber implementation, canonical reviewer gate, landing, runtime smoke and postcommit readback.

The deterministic local rails also exist in:

```text
agent/code_workflow.py
```

Verified classes include `PreflightGate`, `GoalLedger`, `FaberGoalRegistry`, `GovernedCodeRunner`, `ReviewVerdict`, `ReviewEvidence`, `LandingEvidence`, `DefinitionOfDone`, and `HandoffStore`.

**Live-wrapper verdict:** the actual 13-step Autocoder orchestrator entrypoint was not found in the target repo or `$HERMES_HOME` during this read-only inventory. The skill itself says not to call Autocoder active until the entrypoint and all gates are verified in target runtime. Therefore the workflow is `NORMATIVE + PARTIALLY IMPLEMENTED RAILS`, not yet proven as one live end-to-end orchestrator.

## Canonical 13-step mapping

| Step | Canonical workflow | Existing rail/skill | Current evidence | Gap/status |
|---:|---|---|---|---|
| 1 | Directive | `mission-control-planning`, `mwp-uosh-orchestration` | MWP task/case model exists | MWP directive adapter needs durable control-plane binding |
| 2 | Job discovery | `preflight-governance`, `governed-project-orchestration`, `hermes-inventory-runtime-verification` | Read-only discovery procedures exist | Full live wrapper not found |
| 3 | Ranking/planning/architecture | `asi-orchestration`, `mission-control-planning` | Three-axis planning contract exists | Cortex/Executive/Planner/Architect live route not proven |
| 4 | PRE-rails | `preflight-governance`, `governed-agent-code-workflow` | `PreflightGate` + tests exist | adapters must return authoritative live refs |
| 5 | BL gate | `autocoder-13-step-workflow`, `preflight-governance` | contract requires existing BL/allocator | authoritative allocator/runtime path not proven |
| 6 | Claim/lease | Kanban/worktree + `governed-cross-host-code-workflow` | Kanban claims/leases/worktree isolation exist | MWP control-plane binding not wired |
| 7 | Sol design/review/PASS | `autocoder-13-step-workflow`, `governed-agent-code-workflow`, `reviewer-contract-v1` | Sol gate contract exists; tests use reviewer evidence | actual Sol model/provider route not live-verified |
| 8 | Faber implementation | `faber-coding-context-compiler`, `governed-faber-hermes-integration`, `governed-autocoder-execution` | Faber goal/runner/code projection exists | actual target runtime/entrypoint not proven |
| 9 | Governance | `preflight-governance`, `reviewer-contract-v1`, `asi-orchestration` | owner/security/production/irreversible stop rules exist | full three-axis governance adapter open |
| 10 | Canonical reviewer gate | `reviewer-contract-v1` | exact diff/reviewer/evidence requirements exist | reviewer model routing and live invocation open |
| 11 | Landing | `agent/code_workflow.py`, Autocoder skill | `LandingEvidence`, DoD and explicit paths exist | commit closer/Brain/ChangeLog/SelfState runtime chain open |
| 12 | Deploy/runtime smoke | `governed-autocoder-execution`, `cross-runtime-gui-integration`, `symbiose-runtime-integration-verification` | layered verification rules exist | target runtime and actual changed-path smoke open |
| 13 | Postcommit/readback | `governed-agent-code-workflow`, `hermes-learning-bridge-observability` | readback contract exists | actual Brain/Symbiose/ChangeLog/SelfState chain open |

## Role workflow

```text
GPT Sol / design
  → design review + PASS
  → GPT Luna / bounded Faber implementation
  → tests + evidence
  → GPT Sol or Claude / independent Reviewer Contract PASS
  → conditional second opinion
  → owner gate if required
  → landing
  → runtime smoke
  → postcommit/readback
  → measure
  → learn
```

The labels Sol/Luna/Claude are workflow roles until live model/provider resolution is recorded. Reviewer Contract v1 is the canonical gate and cannot be replaced by a Sol PASS alone.

## Relevant skill families found

### Core orchestration/governance

- `autocoder-13-step-workflow`
- `asi-orchestration`
- `mwp-uosh-orchestration`
- `per-user-autonomous-orchestration`
- `governed-autonomous-execution`
- `governed-project-orchestration`
- `mission-control-planning`
- `preflight-governance`
- `reviewer-contract-v1`

### Code/Faber execution

- `governed-agent-code-workflow`
- `governed-autocoder-execution`
- `faber-coding-context-compiler`
- `governed-faber-hermes-integration`
- `governed-cross-host-code-workflow`
- existing `agent/code_workflow.py`

### Runtime/Symbiose/learning/Desktop

- `symbiose-runtime-integration-verification`
- `cross-runtime-gui-integration`
- `desktop-agent-integration`
- `hermes-learning-bridge-observability`
- `hermes-inventory-runtime-verification`
- `desktop-update-data-preservation`
- `symbiose-agent-registry-validation`
- `hermes-learning-observability`
- `desktop-learning-observability`

### Supporting discovery/verification

- governed system reconciliation/closeout skills;
- runtime artifact and runtime-loop audit skills;
- agent-bridge integration skills;
- memory durability diagnostics;
- source-authority verification;
- codebase inspection, planning, TDD and review skills.

The repo also contains 82 bundled and 111 optional `SKILL.md` packages; the list above is the relevant workflow subset, not a claim that every unrelated domain skill belongs in the autonomy pipeline.

## Reuse rule

Do not create a second 13-step workflow. Build the MWP Control Plane adapter around:

```text
autocoder-13-step-workflow (normative sequence)
+ agent/code_workflow.py (deterministic rails)
+ reviewer-contract-v1 (canonical final gate)
+ Kanban (task/lease/worktree authority candidate)
+ verification_evidence (evidence authority)
+ existing ingest/memory/Symbiose routes
```

## Immediate next discovery target

Locate/verify the actual Autocoder wrapper on the authoritative runtime host, including:

```text
entrypoint
active process
model/provider resolver
Sol design route
Luna/Faber build route
reviewer route
second-opinion trigger
landing/commit closer
runtime smoke
postcommit/readback
```

If no wrapper exists, implement only a thin adapter around the existing rails; do not reimplement the 13-step semantics.

## Status

`WORKFLOW FOUND / SKILL STACK MAPPED / LIVE WRAPPER UNVERIFIED`
