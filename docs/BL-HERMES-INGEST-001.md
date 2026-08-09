# BL-HERMES-INGEST-001 — Four-plane canonical ingest

**Status:** `PARTIAL / CANARY_COMPLETE_PRODUCER_WIRING_OPEN`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-INGEST-001 → ADR-HERMES-INGEST-001`
**Mutation policy:** metadata-only until authority, provenance and rollback are verified

| Gate | Requirement | Initial status |
|---|---|---|
| G1 | All Hermes entrypoints emit the canonical envelope | `UNVERIFIED` |
| G2 | Chat/session events are normalized and scoped | `UNVERIFIED` |
| G3 | User facts, corrections, consent and feedback are normalized | `UNVERIFIED` |
| G4 | Cortex/system observations, goals and learning signals are normalized | `UNVERIFIED` |
| G5 | Agent observations, outcomes and handoffs are normalized | `UNVERIFIED` |
| G6 | Schema, identity, scope, consent and provenance validation is fail-closed | `PARTIAL` |
| G7 | Idempotency, deduplication and version conflict behavior is verified | `OPEN` |
| G8 | Canonical authority routing is verified per memory class | `BLOCKED_UNTIL_AUTHORITY` |
| G9 | Candidate → evaluation → promotion/tombstone path is verified | `PARTIAL` |
| G10 | Graph/vector/GNN/context projections have labelled receipts | `BLOCKED` |
| G11 | Runtime effect is measured back through Hermes | `UNVERIFIED` |
| G12 | Degraded, quarantine and dead-letter behavior is verified | `OPEN` |
| G13 | `.14` web, PC/laptop Desktop and gateway use canonical Hermes session/backplane | `UNVERIFIED` |
| G14 | Hermes/Cortex/agent learning events use the envelope and scoped promotion | `UNVERIFIED` |
| G15 | Normal chat memory retrieval/capture is implicit and does not require model-visible tools | `UNVERIFIED` |
| G16 | Explicit memory tools are reserved for intentional inspection/correction/export/mutation | `UNVERIFIED` |
| G17 | Hermes SQLite/FTS5 baseline and latency budget are measured | `OPEN` |
| G18 | Cache hierarchy is scope/version-safe and stale state is labelled | `OPEN` |
| G19 | Remote graph/Qdrant/GNN enrichment is bounded async and cannot stall chat | `OPEN` |
| G20 | Outbox/async writes and learning promotion stay off the synchronous turn path | `OPEN` |
| G21 | Hermes MemoryManager lifecycle events emit validated metadata-only MWP receipts | `IMPLEMENTED_NOT_WIRED` |
| G22 | Web/Desktop/CLI/gateway/cron/delegation each provide a live lifecycle receipt | `OPEN` |
| G23 | Provider selection, timeout, fallback and authority are read back from runtime | `OPEN` |
| G24 | Every implementation step invokes the holistic industry/SOTA/ASI/cross-plane gap gate | `CANONICAL_PREFLIGHT_WIRED_TEST_CONFIRMED_LIVE_INVOCATION_OPEN` |
| G25 | Neo4j/Qdrant/GNN/schema/ingest/surface compatibility is checked as one system | `OPEN` |
| G26 | Hermes chat dogfooding uses governed MWP context only after authority/latency/scope/read-after-write gates | `BLOCKED_UNTIL_RUNTIME_AUTHORITY` |

Closeout requires every required producer and consumer to provide metadata-only receipts. Parent MWP closeout is prohibited while this lane is unresolved.
