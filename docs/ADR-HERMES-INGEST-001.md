# ADR-HERMES-INGEST-001 — One typed ingest envelope before memory and learning

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED / LIVE_WRITER_CANARY`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `CAD-HERMES-INGEST-001`

## Context

Chat, user feedback, Cortex observations and agent outcomes have different semantics and authority. If each module ingests directly, the system will produce duplicate facts, mixed scopes, missing provenance and untraceable learning promotion.

## Decision

All four planes use one versioned, typed, metadata-bearing ingest envelope after entering through the Hermes engine. Consumers may add domain-specific payload schemas behind the envelope, but they may not bypass the common identity, scope, provenance, idempotency and routing contract.

```text
Hermes engine
  → IngestEnvelope v1
  → validation/quarantine
  → canonical authority
  → projections and learning candidates
```

The envelope is not itself a memory store. It is the durable boundary/event contract that makes downstream memory and learning structurally correct from the start.

## Canonical fields

- event identity: `event_id`, `event_type`, `schema_version`
- runtime path: `hermes-agent-engine`
- correlation: `correlation_id`, `causation_id`, `idempotency_key`
- topology: `principal_id`, `tenant_id`, `system_scope`, `session_id`, `conversation_id`, `agent_id`, `cortex_ref`
- semantics: `plane`, `memory_class`, `sensitivity`, `operation`
- source/provenance: `source_ref`, `writer_ref`, `observed_at`, `provenance_ref`, consent state
- routing: `canonical_authority_ref`, target layer and policy
- lifecycle: status, expected version, rollback and receipt references

## Consequences

This creates one stable ingest contract for current and future modules: memory, learning, goals, evidence, task state, world-model updates and projections. It also makes it possible to quarantine uncertain records without polluting canonical truth.

The contract does not claim that all runtime producers are currently wired. Wiring, live authority and read-after-write remain BL gates.
