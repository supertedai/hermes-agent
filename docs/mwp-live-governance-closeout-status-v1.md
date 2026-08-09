# MWP/UOSH Live Governance Closeout Status v1

**Date:** 2026-08-09  
**Parent:** MWP-UOSH-001  
**Status:** `PARTIAL_WITH_LIVE_CANARY_EVIDENCE`

## Current truth

This status is the shared addendum for the MWP, CAD, ADR and BL artifacts. It supersedes stale initial readback wording while preserving the distinction between architecture, canary evidence and production readiness.

| Plane/gate | Current status | Evidence / blocker |
|---|---|---|
| G0 remote/thread parity | `COMPLETE` | Durable session/thread parity readback |
| G1 writer authority | `COMPLETE_CANONICAL_WRITER_CANARY` | Canonical write/retraction/readback 200; audit `ALLOWED` receipts verified; broad per-user/tenant promotion remains gated |
| Lateral bus | `LIVE_READ_ONLY_PRINCIPAL_SCOPED` | `/lateral-bus/status` and `/lateral-bus/read`: 200 with `X-User-ID`; 401 without principal; metadata-only/read-only |
| Hermes writer client | `LIVE_ACTIVE` | `symbiose_write` propagates `X-User-ID`; runtime restarted and healthy |
| G2 Git landing | `SURFACE_AUTH_PRESENT_CLI_HANDOFF_OPEN` | `.13` GitHub surface is owner-confirmed; isolated allowlist is ready; SSH/Keychain CLI handoff is not bound |
| G3 graph | `COMPLETE_CANARY_ROLLED_BACK` | Neo4j/Qdrant/GNN canary synced, deleted, and read back absent |
| G4 Obsidian | `COMPLETE_METADATA_ONLY_PROJECTION` | Active vault `/Users/morpheus/Documents/Brain`; projection read-after-write verified |
| Normal per-user production writes | `NOT_UNLOCKED` | Canary proves route, not all principals/tenants/scopes |
| GNN | `DERIVED_ONLY` | No direct canonical writer; promotion remains fail-closed when collapsed/abstaining |
| Full runtime producer receipts | `OPEN` | Canary receipt exists; all producer/surface receipts are not yet proven |

## Artifacts

- `docs/mwp-g1-writer-authority-readback-v1.json`
- `docs/mwp-g2-git-scoped-landing-preflight-v1.json`
- `docs/mwp-g3-graph-canary-readback-v1.json`
- `docs/mwp-g4-obsidian-projection-preflight-v1.json`
- `docs/mwp-formal-closeout-readback-v1.json`
- `docs/mwp-memory-ingest-dataplane-surface-landing-manifest-v1.json`

## Git

The private target remains `supertedai/AGI`. The isolated landing worktree contains the scoped allowlist, but no commit or push was performed because existing SSH keys do not authenticate to GitHub. No credentials were copied, generated or exposed.

## Obsidian

The active vault was discovered from the Obsidian registry. A new metadata-only projection was written to:

`/Users/morpheus/Documents/Brain/MWP/receipts/mwp-g4-projection-readback-v1.md`

The projection is human-readable, provenance-labelled and not canonical authority.

## Operating rule

Reads are available where live routes and scope permit. Writes use the orchestrator single-writer path and remain scoped, receipt-bearing, idempotent and rollback-capable. No blanket unrestricted write mode is claimed.
