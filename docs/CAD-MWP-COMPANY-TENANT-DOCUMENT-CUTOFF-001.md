# CAD-MWP-COMPANY-TENANT-DOCUMENT-CUTOFF-001 — company tenants, document knowledge and Opus cutoff

**Status:** `PROPOSED / IMPLEMENTATION-GATED`
**Parent MWP:** `MWP-UOSH-001`
**Parent gap:** `GAP-TENANT-SURFACE-ARCH-001`
**Parent CAD:** `docs/mwp-cad-tenant-control-plane-and-surface-architecture-v1.md`
**Parent ADR:** `ADR-MWP-CANONICAL-EVIDENCE-LEDGER-001`
**Parent BLs:** `BL-HERMES-MEMORY-FABRIC-001`, `BL-MWP-CANONICAL-EVIDENCE-LEDGER-001`
**Owner:** Morten / canonical MWP control-plane authority
**Provenance:** user directive in current Hermes conversation; live `/documents`, `/life-contract/steward-context`, MWP gap-register and evidence-ledger readbacks

## 1. Decision intent

Establish two isolated company tenants:

```text
CompanyTenant: energy-rent-as
CompanyTenant: byopus-as
```

Each tenant receives its own document source space, domain/steward binding, connector policy, evidence/provenance scope, retrieval namespace, proposal queue, retention policy and cutoff/export contract. Neither company is modelled as a Personal LifeContract domain, and neither company corpus is copied into global Opus memory by default.

This CAD is an architecture proposal. It does not create a tenant, agent, steward, connector, graph node, Obsidian note or production runtime.

## 2. Target topology

```text
Canonical login/control plane
  ├── Personal tenant (Morten LifeContract)
  ├── Opus System tenant
  ├── energy-rent-as
  │    └── energy-rent-steward / domain-agent
  └── byopus-as
       └── byopus-steward / domain-agent
```

The company steward may read and interpret only its company scope and may return bounded projections to Opus:

```text
status · KPI · risk · blockers · decision_requests · approved links
```

Raw company documents, customer data, employee data, credentials and detailed logs do not cross into Personal or global Opus memory without an explicit policy/consent gate.

## 3. Document ingest contract

```text
source file/folder
→ company tenant + domain classification
→ principal/role/ACL
→ encrypted Vault envelope
→ reference OR ingest zone
→ decrypt gate
→ extract/OCR
→ chunk/version/hash
→ per-tenant Qdrant projection
→ world-model entities/variables/edges
→ DocumentFinding + evidence links
→ proposal queue
→ human/company approval
→ bounded promotion
```

Every document record must retain `tenant_id`, `legal_entity_id`, `domain_id`, `steward_id`, `document_id`, `version`, `content_hash`, source reference, ACL, sensitivity, retention class, parser/embedding versions, provenance and rollback/tombstone reference.

`reference` means encrypted source-on-demand. `ingest` permits extraction and indexed/world-model projection after gates. Ingested knowledge remains a candidate until evidence, confidence, conflict and promotion rules are satisfied.

## 4. Cutoff and evacuation contract

A company cutoff must be a first-class lifecycle, not a UI hide:

```text
CUTOFF_REQUESTED
→ FREEZE_INGEST
→ FREEZE_CONNECTORS
→ EXPORT_PACKAGE
→ EXPORT_INTEGRITY_VERIFIED
→ RESTORE_DRILL_VERIFIED
→ REVOKE_ACCESS
→ PURGE_RUNTIME_PROJECTIONS
→ PURGE_OR_TOMBSTONE
→ READ_AFTER_CUTOFF
→ RUNTIME_RELEASED
```

`RUNTIME_RELEASED` and `DATA_PURGED` are separate statuses. Legal retention and audit tombstones may remain where required, but they must not retain raw company content in Opus retrieval/context paths.

## 5. Non-goals

- no automatic company-agent activation;
- no unrestricted cross-tenant retrieval;
- no automatic skill promotion from a document;
- no autonomous legal, financial, employment, publication or external-send action;
- no new graph/Obsidian writer by this CAD;
- no claim that a configured endpoint is a live canonical world-model authority.

## 6. Acceptance boundary

Promotion beyond `PROPOSED` requires:

- authenticated company-tenant owner/authority readback;
- per-company steward-agent binding read-after-write;
- document upload, list, ingest and delete canary with receipt;
- per-tenant Qdrant and world-model projection readback;
- cross-tenant negative-path test;
- evidence/proposal provenance readback;
- encrypted export and structural restore test;
- cutoff purge/tombstone and post-cutoff negative retrieval test;
- graph and Obsidian destination-specific receipts;
- existing parent BL gates updated and closed only with live evidence.

Current status remains `PROPOSED / IMPLEMENTATION-GATED`.
