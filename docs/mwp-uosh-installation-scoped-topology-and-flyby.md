# MWP-UOSH — installation-scoped user topology and flyby contract

## Purpose

Every Hermes Desktop installation must maintain an isolated per-user topology
readback. The same user id on two Desktop installations must never implicitly
share a topology snapshot, route, connector state, or runtime assumption.

## Identity

```text
installation_id + login_surface_id + principal/user_id
```

The default installation id is a stable hash of the resolved `HERMES_HOME`.
`HERMES_INSTALL_ID` may explicitly name an installation. The login surface is
explicitly set with `HERMES_LOGIN_SURFACE_ID`, or derived from the Hermes
surface/interface/host. Snapshots are written under:

```text
$HERMES_HOME/mwp/user-topology/<installation_id>/<login_surface_id>/<user_id>.json
```

This keeps the same user separate across laptops and also across Desktop, TUI,
web, SSH, gateway, or other login surfaces on one installation.

## Startup readback

The main Hermes agent performs a read-only startup scan for the principal:

```text
user
  → Life Contract
  → user domains
  → domain → steward-agent binding
  → memory-layer readback
  → runtime host reachability (.12/.13/.14/.15)
```

A `BLOCKED` snapshot is a valid readback state. It means the topology is known
to be incomplete and must not be treated as green. It does not abort Hermes
startup. Missing principal identity is a hard error.

## Authority split

- **MWP-UOSH:** canonical governance contract, coverage ledger, acceptance
  criteria, provenance, owner/scope rules, and closeout state.
- **Hermes runtime:** startup hook, scanner implementation, local snapshot and
  session navigation context.
- **Symbiose `.12`:** Life Contract, Neo4j/Qdrant/GNN and memory-layer sources.
- **`.13`:** Morten/Morpheus Desktop and local agent/MCP runtime.
- **`.14`:** web/chat proxy surface and SSH bridge to `.15`.
- **`.15`:** Hermes gateway/dashboard/TUI runtime host in the current fleet.

## Flyby contract

A flyby arriving during active primary work is classified and dispatched to a
bounded leaf subagent when non-trivial. The main loop continues. Only the
short, metadata-only digest is inserted at a safe insertion point; raw child
transcripts are never injected. Blocking corrections are escalated immediately;
future work becomes a queued task/subgoal with provenance.

See Hermes skill `flyby-subagent-routing` for the operational procedure.

## Current known gate

The live Morten readback is currently `BLOCKED` because `IOT` has no resolved
steward binding. Other returned domains and the 20-layer memory readback were
live in the latest smoke test. This is an explicit gate, not a hidden fallback.

The system-topology readback also keeps these per-user surfaces explicitly
open until they are live-read and principal-scoped:

```text
user_cortex
user_learning_state
user_goal_state
```

The presence of Cortex, learning daemons, or goal tables is not evidence that
Morten's current user-scoped state was read. Promotion requires a live
principal-scoped readback for each surface.
