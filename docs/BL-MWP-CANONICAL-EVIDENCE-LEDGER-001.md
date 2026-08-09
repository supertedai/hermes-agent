# BL-MWP-CANONICAL-EVIDENCE-LEDGER-001 — no governed event without a receipt

**Status:** `OPEN / RUNTIME-WIRING-PENDING`
**Parent:** `MWP-UOSH-001 → ADR-MWP-CANONICAL-EVIDENCE-LEDGER-001`
**Mutation policy:** metadata-only until ledger authority/read-after-write is proven

## Gates

| Gate | Requirement | Status |
|---|---|---|
| E1 | Canonical receipt schema and redaction policy | `COMPLETE_CONTRACT` |
| E2 | Hermes Desktop/GPT Luna turn receipts | `PARTIAL` |
| E3 | MemoryManager prefetch/recall/use/effect receipts | `OPEN` |
| E4 | Cortex/world-model and role/provider receipts | `BLOCKED` |
| E5 | Lease/workflow/commit receipts | `PARTIAL` |
| E6 | Git remote read-after-write receipts | `PARTIAL` |
| E7 | Graph write/read-after-write/rollback receipts | `BLOCKED` |
| E8 | Obsidian projection/readback receipts | `BLOCKED` |
| E9 | Reconciler retry/dead-letter/drift receipts | `OPEN` |
| E10 | Source→image→runtime hash parity after recreate | `BLOCKED` |
| E11 | Ledger durability, query and alerting | `OPEN` |

## Hard rules

1. No `COMPLETE` without a receipt.
2. No promotion without source, authority, provenance, effect and rollback.
3. No graph/Obsidian/Git claim from a health endpoint alone.
4. Timeout/abort is terminal and fail-closed.
5. Missing or stale receipt creates `BLOCKED` plus owner/evidence/next_action.
6. Raw prompts and secrets never enter the ledger.

## Required canary

```text
GPT Luna/Hermes Desktop turn
→ active-turn receipt
→ MemoryManager prefetch/sync
→ Cortex metadata receipt
→ scoped Git commit/readback
→ graph receipt/read-after-write
→ Obsidian projection/readback
→ final effect or rollback receipt
```

The BL remains open until the canary and its negative paths are live verified.
