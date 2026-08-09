# ADR-MWP-DATA-PLANE-001 — Canonical schema, projections and measured retrieval

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`
**Parent:** `CAD-MWP-DATA-PLANE-001`

## Decision

Canonical schemas and events are authoritative. Neo4j, Qdrant and GNN are governed projections/derived services with explicit version, provenance, scope and rebuild contracts.

A schema change is a change-gate, not a local convenience:

```text
schema proposal
→ compatibility/lint/conformance
→ migration plan + rollback
→ shadow/backfill
→ projection validation
→ owner approval
→ bounded activation
→ read-after-write/read-after-rebuild
```

A Qdrant score or GNN rank is never itself evidence that a memory/fact is true. Retrieval and reasoning results must retain canonical references and epistemic status.

## Consequences

This allows the data plane to become powerful without becoming opaque: graph captures relations, Qdrant supports semantic retrieval, GNN supports structural ranking, and Hermes receives a scoped projection. Each can fail or drift without silently rewriting truth.

## Rejected alternatives

- treating 110 Qdrant collections as automatically governed because they exist;
- allowing each collection to invent its own identity/scope fields;
- treating GNN output as canonical memory;
- mass-normalizing stores before authority and rollback are proven;
- using health HTTP 200 as data quality evidence.

Production writers remain gated by `BL-MWP-DATA-PLANE-001`.
