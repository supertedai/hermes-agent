# BL-HERMES-SURFACE-BACKPLANE-001 — Cross-surface parity and authority

**Status:** `OPEN`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-SURFACE-BACKPLANE-001 → ADR-HERMES-SURFACE-BACKPLANE-001`

| Gate | Requirement | Status |
|---|---|---|
| G1 | `.14` web surface identity/session binding | `UNVERIFIED` |
| G2 | PC Desktop identity/session binding | `UNVERIFIED` |
| G3 | Laptop Desktop identity/session binding | `UNVERIFIED` |
| G4 | Common Hermes engine/control route | `UNVERIFIED` |
| G5 | Shared backplane event/session continuity | `UNVERIFIED` |
| G6 | Local cache/offline replay idempotency | `OPEN` |
| G7 | Cross-surface read-after-write and freshness | `BLOCKED_UNTIL_AUTHORITY` |
| G8 | Per-device/installation/tenant isolation | `BLOCKED_UNTIL_LIVE_READBACK` |
| G9 | Known-good Desktop rollback baseline preserved | `OPEN` |
| G10 | Existing web remains operational baseline while P1 is blocked | `COMPLETE_BY_POLICY` |
| G11 | Desktop front layer shadow/canary uses same auth/session/backplane | `BLOCKED_BY_P1` |
| G12 | Web→Desktop cutover has parity, health and rollback receipts | `BLOCKED_BY_P1` |

No gate is `COMPLETE` from UI visibility alone. Closeout requires metadata-only live receipts and explicit canonical authority evidence.
