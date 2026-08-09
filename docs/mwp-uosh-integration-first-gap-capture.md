# MWP-UOSH-001 — Integration-first gap capture

## Core decision

Assume existing capability/data first. Do not rebuild a subsystem until discovery proves it is absent or unusable. Most MWP gaps are expected to be:

```text
EXISTS_BUT_UNWIRED
EXISTS_BUT_UNVERIFIED
EXISTS_BUT_WRONG_SCOPE
EXISTS_BUT_WRONG_WRITER
EXISTS_BUT_STALE
EXISTS_BUT_CONFLICTING
MISSING
```

## Gaps to capture without assuming absence

### G-01 — Three-axis identity and scope

Map every record to:

```text
principal/user
system/Cortex
agent/steward
profile
session
project/domain/tenant
```

### G-02 — Cross-axis traversal

Define when and how:

```text
user memory ↔ agent memory ↔ system worldmodel
```

is readable, writable, promotable or denied.

### G-03 — Memory-layer contract

For all 20 layers capture:

```text
storage, writer, reader, instances, scope, provenance,
confidence, freshness, conflict, consolidation,
correction/deletion, runtime test, acceptance
```

Preserve the distinction between own, reachable, blind, absent and unconnected.

### G-04 — Source/ingest lineage

Reconcile existing upload/API/RSS/paper/repo/web/graph/agent ingestors to one source registry and destination policy. Capture owner, encryption, consent, sensitivity, injection scan, transform, cursor, dedupe and deletion.

### G-05 — Cognition/event contract

Unify existing sensing, reasoning, goals, learning insights, proposals, approvals, actions, outcomes, calibration and rollback records. Keep proposal/approval/action/outcome separate.

### G-06 — Learning promotion

Define how a measured outcome becomes:

```text
candidate → evaluated → reviewed → promoted → monitored → rolled back
```

and which axis receives it: user, agent, system or multiple filtered projections.

### G-07 — Agent steward contract

For each agent map:

```text
identity
owned domains
sources
memory instances
readers
writers
tools
goals
approval gate
outcome recorder
system/user traversal
```

### G-08 — Surface parity

Map web, Desktop, gateway, TUI, Faber and Symbiose to the same logical contracts. A surface must not silently maintain a divergent state.

### G-09 — Service topology

Map `.40` hosts/services, process owners, API instances, graph/Qdrant/GNN boundaries, profiles, runtime homes and writer roles.

### G-10 — Governance/provenance

Map every existing BL/ADR/CAD/graph record to the three axes and MWP task. Detect historical/stale/conflicting records before reusing them.

### G-11 — Desktop control plane

Inventory controls as views/actions/gates. Preserve the underlying owner; do not move authority into renderer state.

### G-12 — Update/recovery safety

Ensure Desktop, gateway, agent and graph updates are versioned, compatible, canaried and reversible.

### G-13 — Observability/readback

Every major transition needs metadata-only readback:

```text
status, owner, scope, stage, count, provenance,
freshness, confidence, gate, evidence, next step
```

### G-14 — Negative paths

Test missing identity, wrong user, blind layer, stale source, duplicate ingest, conflicting writer, partial write, restart, deletion and rollback.

## Integration rule

For each gap, first search for existing implementation/data/reader/writer. Only then classify as `MISSING`. Any new adapter must cite the reused source and preserve its authority.

## Status

`INTEGRATION-FIRST / GAP CAPTURE ACTIVE`
