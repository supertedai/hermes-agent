# BL-HERMES-LEARNING-LOOPS-001 — Learning-loop census and runtime effect

**Status:** `OPEN`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-LEARNING-LOOPS-001 → ADR-HERMES-LEARNING-LOOPS-001`

| Gate | Requirement | Status |
|---|---|---|
| G1 | Census Hermes memory/feedback/skill/patch loops | `OPEN` |
| G2 | Census Opus/Cortex goals/world-model/learning loops | `OPEN` |
| G3 | Census agent/steward role/task/outcome loops | `OPEN` |
| G4 | Every producer emits typed ingest events | `UNVERIFIED` |
| G5 | Scope and canonical owner are resolved per event | `PARTIAL` |
| G6 | Candidate/evaluation/promotion/tombstone lifecycle | `PARTIAL` |
| G7 | System/user/chat/agent projections are isolated | `UNVERIFIED` |
| G8 | Retrieved learning is shown to affect a later decision | `UNVERIFIED` |
| G9 | Skill/patch promotion has independent verification | `PARTIAL` |
| G10 | Rollback and correction propagate to projections/cache | `OPEN` |
| G11 | `.14`/Desktop surfaces expose consistent learning status | `UNVERIFIED` |

Closeout requires producer inventory, route receipts, scoped projection receipts, effect measurement and rollback evidence. Event count or local file changes alone cannot close this BL.

## 2026-08-10 write-side owner-stamp delta (Symbiose BL-4015)

Turn and memory-write queue rows are now self-describing: each row carries `principal` and
`stamp_basis`, where `stamp_basis` distinguishes identity threaded in by Hermes
(`init_kwargs`) from identity looked up in the session registry (`session_registry`) from
"not known" (`unstamped`) from "identity infrastructure down" (`lookup_failed`). No default is
ever written.

The pre-existing owner map, built from authenticated `.14` origin, RETAINS AUTHORITY
(ADR-044 D5: principal MEASURED, never caller-asserted — and the provider on `.15` is the
caller). The stamp may only (a) fill rows the map answered on but was silent about, and
(b) report disagreement. On disagreement the MEASURED value is preserved and the dispute is
recorded alongside it (`attribution_disputed`, `attribution_claim`, `attribution_conflict_at`);
an earlier draft nulled the measured value instead, which would have been a cross-principal
LEAK rather than a fail-closed action, because four live readers use
`coalesce(user_id,'morten')` and return conversation content.

G5 is `PARTIAL`, not `COMPLETE`, for three named reasons:

- rows carry no `event_type` from the required event classes (CAD §"Required event classes"),
  so ownership is stamped on an event that does not know what it is;
- the shape is not `IngestEnvelope v1` (ADR-HERMES-INGEST-001 §"Canonical fields");
- rows with `stamp_basis: unstamped` are still APPENDED to a shared queue rather than
  quarantined — the opposite of the ingest fail-closed rule. This is a KNOWN, UNCLOSED
  fail-open, deliberately not patched blind: a blanket quarantine would silently drop the
  owner's own console/PTY turns, which are legitimately unstamped by design. The correct form
  is narrower and needs a decision, not a reflex.
