# BL-HERMES-CCO-WORKING-MEMORY-001 — CCO/Hermes/MWP turn gate

**Status:** `OPEN / RUNTIME-EVIDENCE-PENDING`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-MEMORY-FABRIC-001 → ADR-HERMES-CCO-WORKING-MEMORY-001`
**Mutation policy:** metadata-only; no promotion or production writer opening

## Gates

| Gate | Requirement | Status |
|---|---|---|
| C1 | Hermes Desktop GPT Luna/session provider and any downstream selected provider are separately read back | `PARTIAL` |
| C2 | Hermes MemoryManager scoped prefetch/context/sync hooks are wired | `PARTIAL` |
| C3 | Active-turn receipt has identity, role, model/provider, memory and Cortex refs | `BLOCKED` |
| C4 | Synchronous model/dispatch leaves have bounded timeout and terminal receipt | `PARTIAL` |
| C5 | Cortex/world-model metadata roundtrip has read-after-write | `BLOCKED` |
| C6 | Adaptive routing/enforcement are advisory/deferred and cannot block chat | `OPEN` |
| C7 | Retrieval → use → measured effect → promotion/rollback is live-proven | `BLOCKED` |
| C8 | Graph/Qdrant/Obsidian projections have per-destination receipts | `BLOCKED` |

## Required evidence

A real turn must produce a metadata-only receipt containing:

```text
conversation_id
session_id
principal_id
tenant_id
system_scope
role_id
agent_id
provider_ref
declared_model_ref
selected_model_ref
working_memory_ref
cortex_ref
memory_layer_id
recorded_at
freshness_seconds
provenance_ref
runtime_effect_ref
rollback_ref
status
```

Allowed terminal statuses:

```text
ACTIVE_TURN_STARTED
COMPLETED_TURN
TURN_TIMEOUT
TURN_ABORTED
```

`TURN_TIMEOUT` and `TURN_ABORTED` are terminal fail-closed states, not successful learning events.

## Runtime safety

- No raw conversation content in receipts.
- No direct graph/Qdrant/Obsidian write from model output.
- No provider declaration is treated as live selection.
- Slow 120B/671B workers remain bounded, secondary and non-blocking to normal CCO chat.
- Adaptive routing and enforcement telemetry may defer, but cannot block a turn or grant authority.
- A memory candidate cannot promote without measured runtime effect, provenance, scope and rollback.

## Closeout rule

This BL is `COMPLETE` only after C1–C8 have live evidence. Until then it remains `OPEN` with explicit blocked lanes and no promotion.
