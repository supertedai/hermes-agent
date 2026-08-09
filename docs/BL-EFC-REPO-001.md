# BL-EFC-REPO-001 — Close EFC repository audit lanes

**Parent MWP:** `MWP-UOSH-001`  
**CAD:** `CAD-EFC-REPO-001`  
**ADR:** `ADR-EFC-REPO-001`  
**Status:** Open / fail-closed

| BL | Scope | Acceptance |
|---|---|---|
| `BL-EFC-REPO-001` | Repo verify CI | green `EFC repo verify` run on clean tree |
| `BL-EFC-REPO-002` | AI council audit | re-enable only after green audit and owner receipt |
| `BL-EFC-REPO-003` | Disabled workflows | intentional/retired/blocked classification plus activation receipts |
| `BL-EFC-REPO-004` | Branch protection/signing | owner decision and configured checks/signing readback |
| `BL-EFC-REPO-005` | Count/version parity | canonical generated counts agree across all surfaces |
| `BL-EFC-REPO-006` | Model comparison | executed same-dataset likelihood comparison with chi2/AIC/BIC/lnK |
| `BL-EFC-REPO-007` | Evaluation aggregation | live Evaluation Ledger current_state receipt |
| `BL-EFC-REPO-008` | Stage-IV solver | production-grade hi_class/Boltzmann capability or scoped blocker |
| `BL-EFC-REPO-009` | Public ledger → graph | evidence-layered read-after-write projection |
| `BL-EFC-REPO-010` | Graph → Cortex/runtime | authenticated consumer/readback receipt |
| `BL-EFC-REPO-011` | EFC meta/ASI ablation | EFC routing/atlas utility vs baseline with independent evaluator |

## Closeout

This BL cannot close on Pages success alone. Every child must be `COMPLETE` or
explicitly `BLOCKED` with owner, evidence and next action.
