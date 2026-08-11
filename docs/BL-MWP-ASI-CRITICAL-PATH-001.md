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

## 2026-08-10 Symbiose/Hermes phase mapping (drift control)

Recorded so this work is MAPPED rather than `PARKED` per the drift-control rule. No phase gate
is advanced by any of it.

| Work | Phase | Status | Note |
|---|---|---|---|
| BL-4007 Symbiose self-state reader (ADR-061 step 1) | P3 | `SIDE_LANE_READ_ONLY` | read-only layer/vitals/goal/playbook inventory into the system prompt and one read tool; no shadow receipt, no effect chain |
| BL-4008 cross-principal READ isolation | P1 | `PARTIAL_SIDE_LANE` | one-process read gate on identity; no tenant, no readback receipt; P1 stays `BLOCKED` |
| BL-4015 per-row principal stamp on write queues | P4 | `SIDE_LANE` | owner stamp only; no `event_type`, not `IngestEnvelope v1`; unstamped rows not quarantined |
| BL-4019 user-overflow drain to per-user Hindsight bank | P4 | `SIDE_LANE` | recovered from live deployment; was running untracked |
| BL-4023 per-session topology block in system prompt | P0/P6 | `SIDE_LANE_VOCABULARY_DIVERGENT` | duplicates the required-topology-binding vocabulary; see the convergence note in ADR-HERMES-SURFACE-BACKPLANE-001 |

Explicitly NOT closed: none of the four P0 rows. The nearest is *Principal/session/device/tenant
authority* — BL-4008 delivers principal isolation on the read side within a single process,
while the row requires authenticated user + durable session + device + login surface +
tenant/system scope. P1 *Memory/learning promotion* is made BROADER, not better: BL-4007 adds
one more live read endpoint with no causal effect chain behind it.
