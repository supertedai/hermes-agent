# ADR-MWP-COMPANY-TENANT-DOCUMENT-CUTOFF-001 — isolate company knowledge and guarantee Opus release

**Status:** `PROPOSED / OWNER-REVIEW / RUNTIME-GATED`
**Parent:** `MWP-UOSH-001`
**Related:** `CAD-MWP-COMPANY-TENANT-DOCUMENT-CUTOFF-001`, `ADR-MWP-CANONICAL-EVIDENCE-LEDGER-001`, `ADR-HERMES-MEMORY-FABRIC-001`
**Parent gap:** `GAP-TENANT-SURFACE-ARCH-001`
**Parent BLs:** `BL-HERMES-MEMORY-FABRIC-001`, `BL-MWP-CANONICAL-EVIDENCE-LEDGER-001`

## Context

The live architecture has a domain/steward document API with encrypted document storage, ingest/reference zones, Qdrant/world-model projections and Daedalus-style bounded outputs. The canonical company-tenant registry and company agent bindings are not yet live-verified. Energy Rent AS additionally requires a sudden cutoff path where company material can leave Opus without losing an independently restorable company archive.

Conversation context, graph mirrors, Hindsight memories, vector projections, world-model facts, proposal records and MWP evidence are separate surfaces and must not be treated as one store.

## Decision

Create one isolated tenant per legal/operational business:

```text
energy-rent-as
byopus-as
```

Use a company-scoped steward for each tenant. Company data is ingested through the existing governed document route and is visible to Opus only through scoped, provenance-bearing projections. Personal, Opus-System and Company tenants remain semantically and technically separated.

Company cutoff is implemented as a reversible export-first lifecycle. No tenant is considered released from Opus until all active connectors, agent bindings, retrieval projections, caches, pending queues and context paths have been revoked/purged or explicitly tombstoned and read-after-cutoff has passed.

## Alternatives rejected

1. Put both businesses under Morten's Personal/WORK domain — rejected: wrong authority and weak cutoff boundary.
2. Put both businesses in one company tenant — rejected: legal/entity and access isolation becomes ambiguous.
3. Copy all company documents into global Opus memory — rejected: violates tenant/provenance/data-minimisation boundary.
4. Treat Qdrant or graph presence as the company system of record — rejected: they are projections unless separately promoted.
5. Delete first and export later — rejected: risks irreversible loss and cannot prove completeness.
6. Let a company steward publish skills automatically — rejected: model-derived learning remains a candidate until evaluation/owner promotion.

## Required receipt chain

```text
company source pre-read/hash
→ tenant/role/ACL receipt
→ encrypted vault receipt
→ ingest receipt
→ chunk/embed/world-model projection receipts
→ finding/evidence receipt
→ proposal/approval receipt
→ export manifest/hash
→ restore receipt
→ revoke/purge receipt
→ post-cutoff negative retrieval receipt
```

Receipts are metadata-only and must not contain raw company document content or credentials.

## Consequences

Positive:

- legal-entity separation is explicit;
- company documents become searchable without becoming global memory;
- Daedalus/ByOpus stewards can produce bounded proposals;
- Energy Rent can be evacuated from Opus with a tested archive;
- graph, vector, world-model, Obsidian and MWP states can be reconciled separately.

Costs:

- two tenant authorities and two steward bindings must be maintained;
- every projection needs scope/freshness/provenance/rollback metadata;
- cutoff requires a real export and restore drill;
- company runtime remains blocked until authority and writer receipts exist.

## Current decision status

`PROPOSED`. No tenant, agent, graph node, Obsidian note, document or runtime writer is created by this ADR.
