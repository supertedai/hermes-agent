# CAD-HERMES-LEARNING-LOOPS-001 — System-wide governed learning

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED`
**Parent:** `MWP-UOSH-001`
**Related:** `CAD-HERMES-INGEST-001`, `CAD-HERMES-MEMORY-FABRIC-001`

## Decision

All existing and future learning loops from Hermes, Opus/Cortex and agents use the canonical Hermes engine → ingest envelope → governed promotion path. The shared backplane is system-wide, but learning projections remain scope-aware.

```text
Hermes loop / Cortex loop / agent loop
              ↓
        Hermes engine
              ↓
     typed learning event
              ↓
 scope + provenance + evaluation
              ↓
 candidate / promotion / rollback
              ↓
 system | user | chat | agent projections
```

## Learning scopes

| Scope | Examples | Broadcast policy |
|---|---|---|
| `system/platform` | routing, tool reliability, skill quality, provider quality | system projection only after evaluation |
| `user` | preferences, corrections, personal facts | user-scoped only unless separately approved |
| `chat/session` | working context, summary, temporary decision | session/context projection |
| `agent/domain` | role learning, task outcome, capability pattern | bound agent/domain projection |

Shared learning infrastructure does not mean every agent receives every event. A promotion must declare owner, scope, evidence, freshness, confidence and rollback.

## Required event classes

```text
memory_retrieved
memory_used
feedback_received
outcome_recorded
learning_candidate_created
skill_changed
patch_proposed
patch_verified
promotion_requested
promotion_approved
rollback_requested
```

## Acceptance boundary

A learning loop is runtime-effective only when the system can prove:

```text
event emitted
→ routed through Hermes
→ scoped retrieval/projection
→ used in decision or patch
→ outcome measured
→ promotion/rollback receipt
```

No ASI or autonomous self-improvement claim follows from event existence alone.
