# ADR-HERMES-CCO-WORKING-MEMORY-001 — GPT Luna in Hermes Desktop behind MWP working memory

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED / LIVE_PROVIDER_READBACK`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-MEMORY-FABRIC-001 → ADR-HERMES-MEMORY-FABRIC-001`
**Related BL:** `BL-HERMES-CCO-WORKING-MEMORY-001`

## Context

The canonical user chat/control surface is Hermes Desktop running GPT Luna. CCO is a separately available backend model at the `.11:8001` runtime endpoint; it is not the user's current Desktop chat model and must not silently replace GPT Luna. Hermes working memory is a lifecycle/context capability, not a model and not a competing canonical store. The environment also declares a local `gpt-oss-120b` world-model/worker and a `cogito-v2-preview-deepseek-671b-moe` reasoner, but neither is evidence of the active Hermes Desktop chat provider.

Recent live logs showed slow synchronous dispatch leaves and model/provider fields missing from active-turn receipts. A model name must not be inferred from environment configuration, a worker declaration or a slow auxiliary call.

## Decision

1. **GPT Luna in Hermes Desktop remains the current user chat/control model.** Its live provider/model identity must be read from the Hermes Desktop/session receipt; it is not inferred from `.11` runtime environment variables.
2. **CCO is an optional downstream backend candidate**, usable only when an explicit governed route selects it and records the selection. It must not replace GPT Luna or take over Desktop control.
3. **Hermes remains the only runtime waist.** `MemoryManager` owns scoped prefetch, context assembly, turn capture, `sync_all` and queued enrichment.
4. **MWP owns governance and durable memory promotion:** principal, tenant, scope, provenance, authority, lease, receipt, rollback and promotion gates.
5. `gpt-oss-120b` and `cogito-v2-preview-deepseek-671b-moe` are secondary declared workers until a separate live provider/role receipt proves their selection. They must not block normal GPT Luna/Hermes Desktop chat.
6. Working memory is injected through Hermes lifecycle hooks; it is not written as raw prompt content into a metadata receipt and is not promoted merely because it was prefetched.
7. Model attribution is split explicitly:
declared_model_ref
selected_model_ref
provider_ref
hermes_desktop_surface_ref
working_memory_ref
cortex_ref
```

The current Desktop control path is GPT Luna through Hermes. A `.11` model such as CCO is a separate downstream candidate and requires explicit route evidence.

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
