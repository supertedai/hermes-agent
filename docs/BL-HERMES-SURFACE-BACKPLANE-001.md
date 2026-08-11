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
| G13 | Single-process cross-principal READ isolation on the gateway surface | `PARTIAL` |

No gate is `COMPLETE` from UI visibility alone. Closeout requires metadata-only live receipts and explicit canonical authority evidence.

## 2026-08-10 read-side isolation delta (Symbiose BL-4008)

One gateway process serves every principal under a single `HERMES_HOME`, and
`gateway/run.py::_resolve_profile_home_for_source` fails OPEN: an explicitly requested profile
that does not exist on disk yields a `logger.warning` and returns the owner's home. The owner's
graph-mirrored `MEMORY.md` (300k+ facts) was therefore served in the system prompt of non-owner
principals. Measured with a real non-owner session id: 7 221 characters, the whole file.

The read side is now gated on IDENTITY, not on file placement: a positively identified
non-owner is denied and receives an explicit boundary notice instead of an empty block
(measured after the fix: 294 characters, no `MEMORY.md`, no self-state). The gate is
deliberately "identified other", NOT "unconfirmed owner" — the stricter form would strip memory
from the owner's own console/PTY sessions, where absent identity is documented upstream as
legacy → owner-default.

G13 is `PARTIAL`, not `COMPLETE`:

- no metadata-only receipt is emitted for the isolation decision;
- there is no `tenant_id` axis — the gate is an allowlist of one principal;
- the WRITE side is still open (see BL-HERMES-LEARNING-LOOPS-001 G5): all principals' turns
  still append to one queue file in the owner's home, and rows with unknown identity are
  written rather than quarantined.

G8 (per-device/installation/tenant isolation) remains `BLOCKED_UNTIL_LIVE_READBACK` and is not
advanced by this.
