# ADR-JS-WM-001 — Route Jetstream through WorldModelHub and Cortex

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`  
**Scope:** MWP-UOSH-001, Jetstream, Hermes ingest, world model, Cortex, agent/domain projections

## Context

Jetstream already discovers external sources and gap-driven information needs.
The system also has a world-model hub and Cortex components. The missing piece
is a governed projection contract between them.

## Decision

Use one metadata-only router contract:

```text
Jetstream
→ Hermes engine
→ canonical ingest envelope
→ provenance/injection/freshness gate
→ entropy or KnowledgeGap trigger
→ canonical WorldModelHub projection
→ Cortex system projection
→ scoped domain-agent projections
→ optional learning candidate
```

Cortex is always the system-level target for an eligible fresh signal. Domain
fan-out occurs only for high-entropy or gap-relevant signals and only to explicit
scoped domain agents.

## Rejected alternatives

- raw broadcast of every Jetstream item to every agent;
- a second world-model writer;
- treating external source text as runtime authority;
- fan-out without provenance, freshness or injection checks;
- automatic memory/graph/skill promotion from Jetstream alone.

## Acceptance

A live implementation requires:

```text
source receipt
+ injection-check receipt
+ entropy/freshness calculation
+ gap relevance
+ WorldModelHub write receipt
+ Cortex readback
+ scoped domain projection receipt
+ no raw payload leakage
+ rollback/quarantine path
```
