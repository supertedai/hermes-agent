# MWP-UOSH — perfect topology question and scanning contract

## Objective

For every Hermes/Symbiose interaction, Opus must be able to answer a topology
question of the form:

> What is where, for this user, installation, login surface and agent, right now?

The answer must distinguish live runtime from declaration, cache, historical
snapshot and unknown state.

## Required identity scope

```text
system_id
installation_id
login_surface_id
principal/user_id
agent_id
session_id (when session-specific)
```

`session_id` is not a substitute for `user_id`; it only narrows a readback.

## Required readback dimensions

```text
CAD/ADR/architecture intent
software services and versions
hardware/runtime hosts
Docker/Compose containers
systemd/launchd/processes/listeners
Neo4j schema/indexes/constraints
Qdrant collections/indexes/health
GNN models, loaders and serving routes
Symbiose APIs and MCP routes
Hermes Desktop/TUI/web/gateway surfaces
Opus/Cortex working state
agent-local world models
ConversationWorkingModel ↔ OpusWorkingMemory
Life Contract domains and steward agents
memory, learning, goals and consent scopes
lateral agent communication
freshness, provenance, version and drift
```

## Evidence states

Every item must be classified as one of:

```text
LIVE          read from the current runtime/authority
CONNECTED     route/identity handshake verified
DECLARED      present in CAD/ADR/schema/config only
CACHED        previous snapshot, not freshly verified
STALE         freshness budget exceeded
DRIFTED       differs from declared/previous topology
BLOCKED       known gate prevents safe use
UNKNOWN       not discovered or not readable
```

No `DECLARED`, `CACHED`, `UNKNOWN` or `STALE` item may be promoted to `LIVE`
without a new readback.

## Discovery and freshness

Startup scanning is necessary but insufficient. The topology service must also
perform periodic read-only discovery/heartbeat and record:

```text
first_seen
last_seen
last_verified
freshness_budget
version/config hash
source authority
observed route
expected route
status transition
```

Docker/container moves, stopped daemons, changed ports, new schemas, new
agents, disconnected buses and changed CAD/ADR must generate metadata-only
drift events and downgrade the affected surface until reverified.

## CAD/ADR alignment

CAD/ADR is intent/evidence, not live runtime. The topology matrix must map each
CAD/ADR item to:

```text
implemented surface
runtime owner
user/agent scope
live route
verification test
rollback/consent gate
current status
known gap
```

A CAD/ADR item without a live route remains `DECLARED` or `UNKNOWN`.

## ASI architecture gates

The ASI target is not considered structurally covered until these are live or
explicitly blocked:

```text
Opus intelligence ↔ Cortex
Cortex ↔ canonical world-model hub
agent-local world model ↔ canonical hub
chat surface ↔ ConversationWorkingModel
ConversationWorkingModel ↔ OpusWorkingMemory
agent ↔ lateral bus ↔ agent
user memory/learning/goals ↔ principal-scoped readback
```

This contract is metadata-only. It does not authorize writes, learning
promotion, agent creation or runtime actuation by itself.
