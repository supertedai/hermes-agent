# CAD-MWP-ASI-CRITICAL-PATH-001 — ASI foundation sequence

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED`
**Parent:** `MWP-UOSH-001`
**Purpose:** Preserve the ASI main goal and prevent side-lane drift.

**Related data-plane lane:** `CAD-MWP-DATA-PLANE-001` / `BL-MWP-DATA-PLANE-001`

## Main goal

Build a governed, learning, memory-bearing Opus/Symbiose system with Hermes as the runtime engine, capable of carrying the user, chat, system/Cortex, agents and world-model projections without competing authorities or breaking updates.

ASI capability is not claimed by this CAD. It defines the prerequisite sequence for an ASI-oriented system substrate.

## Critical path

```text
P0 baseline + topology
  → P1 canonical auth/session/thread parity
  → P2 canonical CRUD/truth/authority
  → P3 Hermes ingest + four-plane memory
  → P4 learning-loop census/promotion/rollback
  → P5 Cortex/agent/Jetstream roundtrips
  → P6 surface parity and Desktop-front web migration
  → P7 graph/Qdrant/GNN/Obsidian governed writers
  → P8 adaptive autonomy and ASI evaluation
```

A later phase may not be declared `COMPLETE` while a required predecessor is unresolved. Independent read-only/preflight lanes may continue.

## Phase gates

| Phase | Required closure | Blocks |
|---|---|---|
| P0 | known-good Desktop/session baseline, topology inventory, rollback | destructive migration |
| P1 | principal/session/device/tenant/login-surface and thread readback across `.14`, PC, laptop | scoped memory/CRUD |
| P2 | canonical writer, idempotency, versions, hashes, outbox, read-after-write, tombstone/rollback | durable memory/learning writes |
| P3 | Hermes engine → ingest envelope → user/chat/system/agent routes | promotion/projection |
| P4 | Hermes/Cortex/agent learning census, scoped promotion and rollback | global/system learning |
| P5 | Chat↔Cortex↔agent and Jetstream→WorldModelHub→Cortex→agent receipts | broad agent autonomy |
| P6 | surface parity, same session/backplane, compatibility/canary/rollback | replacing existing web surface |
| P7 | graph/Qdrant/GNN/Obsidian writer authority, restore and read-after-write | production projections/writes |
| P8 | leases, fleet routing, capability/evaluation, bounded self-improvement | ASI/autonomy claims |

## Side-lane rule

Graph, Obsidian, Jetstream enhancements, new agents, GUI work and external flybys must map to a phase and dependency. If they do not advance the current critical path, they remain parked or read-only shadow work.

## Update safety

Every runtime update uses:

```text
known-good baseline
→ pre-read/hash/backup
→ compatibility check
→ shadow/canary
→ health + session/thread parity
→ controlled activation
→ read-after-write
→ rollback receipt
```

No update may silently replace auth, session, memory or writer authority.
