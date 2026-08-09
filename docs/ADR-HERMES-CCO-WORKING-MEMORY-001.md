# ADR-HERMES-CCO-WORKING-MEMORY-001 — CCO chat-model behind Hermes working memory

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED / LIVE_PROVIDER_READBACK`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-MEMORY-FABRIC-001 → ADR-HERMES-MEMORY-FABRIC-001`
**Related BL:** `BL-HERMES-CCO-WORKING-MEMORY-001`

## Context

The live provider registry currently exposes `cco` at the canonical chat endpoint. Hermes working memory is a lifecycle/context capability, not a model and not a competing canonical store. The environment also declares a local `gpt-oss-120b` world-model/worker and a `cogito-v2-preview-deepseek-671b-moe` reasoner, but neither is evidence of the active chat provider.

Recent live logs showed slow synchronous dispatch leaves and model/provider fields missing from active-turn receipts. A model name must not be inferred from environment configuration, a worker declaration or a slow auxiliary call.

## Decision

1. **CCO remains the current chat-model candidate** only when live model-selection/response evidence identifies `cco` for the turn.
2. **Hermes remains the only runtime waist.** `MemoryManager` owns scoped prefetch, context assembly, turn capture, `sync_all` and queued enrichment.
3. **MWP owns governance and durable memory promotion:** principal, tenant, scope, provenance, authority, lease, receipt, rollback and promotion gates.
4. `gpt-oss-120b` and `cogito-v2-preview-deepseek-671b-moe` are secondary declared workers until a separate live provider/role receipt proves their selection. They must not block normal CCO chat without a bounded gate.
5. Working memory is injected through Hermes lifecycle hooks; it is not written as raw prompt content into a metadata receipt and is not promoted merely because it was prefetched.
6. Model attribution is split explicitly:

```text
declared_model_ref
selected_model_ref
provider_ref
working_memory_ref
cortex_ref
```

A declared ref is not a selected/live ref.

## Required turn lifecycle

```text
turn_start
→ identity/tenant/scope resolve
→ MemoryManager.prefetch_all(scoped)
→ bounded context assembly
→ live model/provider selection
→ CCO chat turn (or explicitly selected secondary worker)
→ Cortex/world-model metadata receipt
→ MemoryManager.sync_all()
→ queue_prefetch_all()
→ retrieval/use/effect evidence
→ promotion or rollback
```

## Required metadata-only receipt

```text
receipt_id
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

Raw prompts, private memory payloads, credentials and sensitive content are excluded.

## Timeout and degraded behavior

All synchronous model/dispatch/world-model leaves must be bounded. On timeout:

```text
ACTIVE_TURN_STARTED → TURN_TIMEOUT
```

The turn must close fail-closed with a terminal receipt. A timeout is not a completed learning event and cannot promote memory. Remote/slow enrichment falls back to the Hermes local baseline and remains `DEFERRED` or `SHADOW`.

## Rejected alternatives

- Replacing CCO with 671B without live provider evidence.
- Treating `gpt-oss-120b` worker availability as active chat-model selection.
- Injecting all memory layers into every prompt.
- Promoting a prefetch or start receipt as learning without retrieval/use/effect evidence.
- Allowing adaptive routing or enforcement telemetry to block chat or open writer authority.

## Acceptance boundary

This ADR is architecture-accepted but runtime-gated. It is not `COMPLETE` until a real turn proves provider/model selection, Hermes working-memory reference, Cortex/world-model reference, bounded completion/timeout, provenance and read-after-write. Promotion remains blocked until the existing Memory Fabric BL proves:

```text
retain → recall → use → measured effect → promotion/rollback
```
