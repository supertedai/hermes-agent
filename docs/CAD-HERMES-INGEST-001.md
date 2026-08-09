# CAD-HERMES-INGEST-001 — Canonical ingest for memory and learning

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED / LIVE_WRITER_CANARY`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `MWP-UOSH-001`
**Related:** `CAD-HERMES-MEMORY-FABRIC-001`, `ADR-HERMES-MEMORY-FABRIC-001`

## Decision

A single canonical ingest pipeline is the front door for all memory, learning and related state signals from the four planes:

```text
chat / user / Cortex-system / agent-steward
                    ↓
              Hermes engine
                    ↓
       canonical ingest envelope
                    ↓
  normalize → classify → scope → provenance
       → schema validate → deduplicate
                    ↓
       route to canonical authority
                    ↓
 memory / learning / task / evidence stores
                    ↓
 graph / vector / GNN / context projections
                    ↓
 metadata receipt + read-after-write/effect
```

No memory or learning module may invent its own incompatible input shape or bypass this envelope. Hermes remains the runtime entry point; the ingest contract is the governed normalization boundary behind it.

## Four-plane routing

| Plane | Typical signals | Default target |
|---|---|---|
| `chat` | turn, message, conversation state, extracted candidate | Hermes session or approved Memory Fabric datatype |
| `user` | preference, correction, consent, personal fact, feedback | user-scoped Memory Fabric / consent authority |
| `system` | Cortex observation, world-model update, goal, calibration, learning signal | Cortex/MWP system authority |
| `agent` | role memory, task observation, capability outcome, handoff result | agent/task authority with explicit projection policy |

The plane is metadata, not authority by itself. Authority is resolved by `memory_class`, scope, policy and canonical datatype mapping.

## Required pipeline stages

1. **Capture** — accept only through Hermes engine and assign correlation/causation IDs.
2. **Normalize** — convert channel/provider-specific input into the canonical envelope.
3. **Classify** — identify plane, event type, memory class and sensitivity.
4. **Bind identity/scope** — principal, tenant, system scope, session, conversation and agent.
5. **Attach provenance/consent** — source, writer, timestamp, evidence and consent/deletion state.
6. **Validate schema/policy** — reject malformed, ambiguous or unauthorized events.
7. **Deduplicate** — enforce idempotency and deterministic event identity.
8. **Route** — send to exactly one canonical authority or quarantine; projections are downstream.
9. **Derive** — create explicitly labelled memory/learning candidates and projections; never silently promote.
10. **Receipt** — emit metadata-only status, version/hash, freshness, projection and rollback refs.
11. **Measure effect** — record whether retrieved learning was used and whether outcome/promotion was verified.

## Fail-closed rules

- Missing identity, scope, provenance, event type or schema version → `REJECTED` or `QUARANTINED`.
- Ambiguous plane or memory class → `QUARANTINED`; do not guess.
- Model inference → candidate only until evaluation/promotion gates close.
- Duplicate idempotency key → return original receipt; do not create a second event.
- Canonical authority unavailable → no local shadow write presented as success.
- Projection failure → canonical and projection states remain distinct (`STALE`, `DIVERGED`, `UNKNOWN`).
- Raw content is never placed in metadata-only receipts.

## Implicit engine path

The canonical ingest envelope is emitted by Hermes lifecycle hooks for normal turn capture, retrieval-use signals and low-risk feedback. A model-visible tool call is not required for the normal path and must not become a latency dependency.

```text
Hermes turn lifecycle
→ implicit capture/prefetch
→ canonical envelope
→ async governed ingest
```

Explicit tools are opt-in interfaces for inspection, correction, export or owner-gated mutation.

## MemoryManager receipt bridge

The existing Hermes MemoryManager lifecycle (`prefetch_all`, `queue_prefetch_all`, `sync_all`) is the only intended runtime entry for MWP memory receipts. The adapter emits metadata only; it does not capture payloads, activate providers, promote candidates or write canonical stores.

```text
MemoryManager lifecycle
→ metadata-only MWP envelope
→ validation/quarantine
→ receipt/readback
→ governed promotion only after authority gates
```

## Surface/backplane entry rule

The envelope is emitted after every supported surface enters the Hermes engine:

```text
`.14` web GUI / PC Desktop / laptop Desktop / gateway
  → canonical auth/session
  → Hermes engine
  → IngestEnvelope v1
```

No surface may directly publish memory, learning, graph or vector mutations to the backplane. Reconnect/replay uses the same idempotency key and returns the original receipt.

## Learning event rule

The ingest pipeline accepts typed learning/evidence events from Hermes, Cortex and agents, including:

```text
memory_retrieved
memory_used
feedback_received
outcome_recorded
learning_candidate_created
skill_changed
patch_proposed
patch_verified
promotion_requested
promotion_approved
rollback_requested
```

Each event is classified to system/platform, user, chat/session or agent/domain scope before routing. It is a candidate or evidence event until the applicable evaluation and promotion gate closes.

## Non-goals

This CAD does not authorize direct graph writes, automatic global learning promotion, bypassing Hermes, separate `.14` authority, or replacing Hermes core. It defines the contract and governance boundary needed before those runtime paths can be closed.
