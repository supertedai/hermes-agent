# BL-MWP-ASI-CRITICAL-PATH-001 — Master phase and drift control

**Status:** `PARTIAL / GATES_OPEN`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `MWP-UOSH-001 → CAD-MWP-ASI-CRITICAL-PATH-001 → ADR-MWP-ASI-CRITICAL-PATH-001`

| Phase | Gate | Initial status |
|---|---|---|
| P0 | baseline/topology/rollback | `OPEN` |
| P1 | auth/session/thread parity | `BLOCKED_UNTIL_LIVE_READBACK` |
| P2 | canonical CRUD/truth | `BLOCKED_UNTIL_AUTHORITY` |
| P3 | Hermes ingest/four-plane memory | `IMPLEMENTED_CONTRACT / UNVERIFIED_RUNTIME` |
| P4 | learning-loop census/promotion | `OPEN` |
| P5 | Cortex/agent/Jetstream roundtrips | `UNVERIFIED` |
| P6 | surface parity and Desktop-front web migration | `BLOCKED_BY_P1` |
| P7 | graph/Qdrant/GNN/Obsidian writers | `BLOCKED_BY_P2` |
| P8 | bounded autonomy/ASI evaluation | `BLOCKED_BY_P1_P2_P4_P5` |

## Required phase receipt

```text
phase_id
predecessor_status
owner
evidence_refs
freshness
canonical_authority_ref
rollback_ref
status
next_action
```

## Drift control

Every flyby, new feature, GUI request, agent, memory layer or external integration must be mapped to a phase. Unmapped work is `PARKED`, not silently added to the critical path.

No parent closeout is allowed while this BL or any predecessor gate remains unresolved.

## 2026-08-09 access/readback update

`docs/mwp-cross-surface-access-readback-v1.json` records the current surface truth: local Git trees and `/home/byopus/AGI` are writable; 102 scoped artifacts are prepared and Git promotion awaits the `.13` GitHub-surface → runtime CLI handoff; graph read is connected and the orchestrator canary is rollback-verified, but canonical writer audit authority remains unverified; lateral-bus HTTP is live principal-scoped/read-only with 200/401 behavior; and the active Brain Obsidian vault has a verified metadata projection. This BL remains `PARTIAL / GATES_OPEN`; no blanket production-write authority is claimed.
