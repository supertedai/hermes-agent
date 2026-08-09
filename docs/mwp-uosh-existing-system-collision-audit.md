# MWP-UOSH-001 — Existing-system collision audit

**Status:** PARTIAL / RECONCILIATION REQUIRED
**Scope:** Git, BL, ADR, CAD, Symbiose graph and Obsidian.

## Current evidence

| Source | Current evidence | Reconciliation status |
|---|---|---|
| Git | Isolated branch `mwp/uosh-automation-01` at `ca939c488`; origin and upstream are known; main target is dirty | Partial; no fetch/remote-head reconciliation performed |
| BL | Existing references include BL-2290, BL-2363, BL-2653, BL-2783/2786/2789, BL-2790, BL-3254, BL-3404, BL-3428, BL-3432, BL-3621 and Faber closeout BLs | Partial; no authoritative full BL registry/owner/closeout mapping yet |
| ADR | Existing source references include ADR-022, ADR-035, ADR-038, ADR-045, ADR-046 | Partial; no authoritative adoption/freshness/owner reconciliation yet |
| CAD | Existing Faber/workflow references use CAD-M; broader CAD-A/C/D/G/M mapping is planned | Partial; no canonical CAD registry readback yet |
| Symbiose graph | Native `graph_query` and gated `symbiose_write` are present; `.12:8010` is reachable as `unified_api` | Not reconciled; live graph authority, writer, provenance and ownership remain unverified |
| Obsidian | Source documents identify Morten's Obsidian vault as a separate curated surface on `.13`; `PreflightGate` requires Obsidian evidence | Not reconciled; no live vault readback or path/owner verification in this audit |

## Collision rules

1. Do not mint a new BL, ADR or CAD identifier locally.
2. Do not create a parallel user store, task database, memory store, graph writer, evidence ledger or scheduler.
3. Treat `MWP-UOSH-001` as a work-package reference only; it is not a BL/ADR/CAD identifier.
4. Reuse existing BL/ADR/CAD when scope and decision match; request owner-gated child records only when needed.
5. Do not claim graph or Obsidian synchronization from source references or tool availability.
6. Do not fetch, merge, reset, clean or push the dirty target while ownership is unresolved.

## Required next reconciliation

- Read authoritative BL/ADR/CAD registries and owner/status/adoption fields.
- Read graph metadata/authority and verify the `.12`/`.13` relationship.
- Obtain authenticated/read-only Obsidian vault evidence on `.13`.
- Compare the isolated MWP case against all matching existing records.
- Record a collision verdict before any live adapter or runtime wiring.
