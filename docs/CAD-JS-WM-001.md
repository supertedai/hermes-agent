# CAD-JS-WM-001 — Jetstream-informed shared world model

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED`
**Related:** `CAD-HERMES-INGEST-001`, `CAD-HERMES-LEARNING-LOOPS-001`

## Architectural decision

Jetstream becomes an external observation and gap-closing input to the shared
world model. It must not fan raw external data directly into every agent.

```text
Jetstream
→ provenance + injection gate
→ entropy/freshness/gap router
→ WorldModelHub
→ Cortex/system view
→ domain-scoped projections
```

## High-entropy and gap rule

A signal is eligible for domain fan-out when:

- freshness is `FRESH`;
- injection screening is verified;
- provenance and payload references exist; and
- entropy meets the configured floor or one or more relevant `KnowledgeGap`
  references exist.

Otherwise it is Cortex-only, quarantined or dropped as stale.

## Domain projection

The router must map a signal to explicit domain-agent IDs. It must not infer
that all agents should receive all signals. Domain projections are metadata and
reference based; domain agents fetch only through their scoped authority.

## Hermes ingest/backplane binding

Jetstream is an external system-observation producer. It enters through the Hermes engine and `IngestEnvelope v1`; it is not a direct memory or graph writer. The resulting event may be routed to WorldModelHub/Cortex and, only after scope/evaluation, become a learning candidate for relevant agents or system projections.

