# BL-MWP-DATA-PLANE-001 — Schema/Qdrant/GNN quality and restore

**Status:** `OPEN / BLOCKED_BY_P2_AUTHORITY`
**Parent:** `MWP-UOSH-001 → CAD-MWP-DATA-PLANE-001 → ADR-MWP-DATA-PLANE-001`

| Gate | Requirement | Initial status |
|---|---|---|
| G1 | Canonical schema registry and owner map | `OPEN` |
| G2 | Entity/event identity, scope and provenance conformance | `OPEN` |
| G3 | Backward/forward compatibility and migration/rollback checks | `OPEN` |
| G4 | Neo4j constraints/indexes/migration validate parity | `PARTIAL` |
| G5 | Qdrant collection inventory mapped to schema/owner/scope | `PARTIAL` |
| G6 | Qdrant vector model/dimension/metric/payload-index conformance | `OPEN` |
| G7 | Stable point/chunk identity and tombstone/rebuild policy | `OPEN` |
| G8 | Qdrant full critical-collection snapshot/restore | `PARTIAL` |
| G9 | Neo4j snapshot/restore and read-after-restore | `OPEN` |
| G10 | GNN feature/model/checkpoint registry and leakage controls | `OPEN` |
| G11 | GNN baseline, calibration, drift and checkpoint restore | `OPEN` |
| G12 | Graph↔vector↔canonical identity/scope parity | `OPEN` |
| G13 | Retrieval baseline: precision/recall/MRR/nDCG/stale-hit | `OPEN` |
| G14 | Projection rebuild, failure and rollback conformance | `OPEN` |
| G15 | Hermes retrieval envelope preserves authority/provenance/epistemic state | `UNVERIFIED` |

Existing evidence is bounded: one isolated Qdrant collection restore is verified; this does not close full Qdrant, Neo4j or GNN restore.

No P7 writer or mass migration may be promoted while P2 authority is unresolved. Parent MWP closeout cannot close this lane on declarations alone.
