# ADR-HERMES-LEARNING-LOOPS-001 — One governed learning path, scoped projections

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`
**Parent:** `CAD-HERMES-LEARNING-LOOPS-001`

## Decision

Hermes' existing memory, feedback, skill and patch loops are treated as first-class learning producers. Opus/Cortex loops and agent/steward loops use the same ingest envelope and promotion/evidence contract.

The canonical backplane receives events; it does not automatically make them global knowledge. Promotion is scoped and routed to the relevant consumer projection.

## Required distinction

```text
learning event
≠ candidate memory
≠ promoted fact
≠ system policy
≠ verified capability
```

Each transition requires its own evidence and rollback reference.

## Rejected alternatives

- allowing each agent to maintain an ungoverned learning writer;
- broadcasting all agent learning globally;
- treating Hermes patch/skill changes as verified solely because they were applied;
- making user or chat memory system-wide by default;
- assuming an event stream proves runtime learning effect.

Runtime census and producer wiring remain open under `BL-HERMES-LEARNING-LOOPS-001`.
