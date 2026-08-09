# MWP-UOSH — continuous CAD/ADR/BL change ledger

## Rule

Every material change, topology drift event, flyby insertion, daemon/service
transition and ASI-alignment update receives a metadata-only change event with:

```text
CAD id
ADR id
BL id
principal/user_id
installation_id
login_surface_id
agent_id
system scope
action/intent
evidence references
status/gap
```

When no canonical CAD/ADR/BL number has been allocated yet, the ledger creates
`CAD-EVT-*`, `ADR-EVT-*`, and `BL-EVT-*` provisional identifiers. They are not
pretended to be authoritative until promoted by the existing MWP/CAD/ADR/BL
registry.

## Destination receipts

An event is `COMPLETE` only when all three destinations return a verified
metadata receipt:

```text
git      → commit/ref + verification
graph    → Neo4j node/edge/ref + verification
obsidian → note/path/ref + verification
```

Missing or unverified destinations keep the event `OPEN` or `BLOCKED`. No
subagent, daemon, or agent may claim that a destination was updated from a
static config line or an attempted write.

## Runtime location

The append-only local MWP journal is installation-scoped and must use:

```text
$HERMES_HOME/mwp/change-ledger/<installation_id>/<login_surface_id>/<user_id>.jsonl
```

The journal is metadata-only; raw code, private memory, credentials and raw
learning/evidence payloads are forbidden.

## Current implementation

```text
agent/mwp_change_ledger.py
tests/test_mwp_change_ledger.py
```

The current implementation validates the contract locally. The git, Neo4j and
Obsidian adapters are still separate integration gates; until they return
receipts, the ASI control spine remains open.
