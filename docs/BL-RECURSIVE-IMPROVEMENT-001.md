# BL-RECURSIVE-IMPROVEMENT-001 — Implement recursive improvement lane

**Parent MWP:** `MWP-UOSH-001`  
**CAD:** `CAD-RI`  
**ADR:** `ADR-RECURSIVE-IMPROVEMENT-001`  
**Status:** Proposed / not runtime-promoted

## Child work items

| BL | Scope | Acceptance evidence |
|---|---|---|
| `BL-RI-001` | Chat/Cortex/world-model round-trip | live provenance + freshness receipt |
| `BL-RI-002` | Memory insight-to-outcome promotion | measured effect + scoped promotion/rollback |
| `BL-RI-003` | Runtime role/provider/instance routing | active-turn and fallback receipt |
| `BL-RI-004` | Fleet liveness/capacity/handoff | independent liveness and reassignment receipts |
| `BL-RI-005` | Goal/task/outcome calibration | joined goal/action/outcome receipt |
| `BL-RI-006` | Experiment/evaluation/promotion loop | baseline/eval/keep-discard/promotion receipt |
| `BL-RI-007` | Source/deploy/runtime parity | commit/runtime/freshness/rollback tuple |
| `BL-RI-008` | Cross-domain capability evaluation | transfer/novelty/robustness/calibration benchmark |
| `BL-RI-009` | Cost/latency/quality routing | route economics and degradation receipt |
| `BL-RI-010` | Corrigibility and goal stability | correction/shutdown/rollback/conflict test receipt |
| `BL-RI-011` | External recursive horizon and internal overoptimization | source scan, adversarial comparison, transfer analysis and evaluation receipt |

## Agent task

`recursive-improvement-scout` is a proposal-only worker for discovery and
research. It creates or updates only bounded metadata/proposal artifacts via
existing MWP authority. It does not directly land code or change runtime.

## Closeout

BL-RECURSIVE-IMPROVEMENT-001 cannot close until every child is `COMPLETE` or
explicitly `BLOCKED` with owner, evidence and next action. A proposal is not a
promotion; a passing local test is not live authority.
