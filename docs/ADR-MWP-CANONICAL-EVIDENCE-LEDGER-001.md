# ADR-MWP-CANONICAL-EVIDENCE-LEDGER-001 — governed evidence for every lifecycle transition

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME-GATED`
**Parent:** `MWP-UOSH-001`
**Related:** `ADR-HERMES-MEMORY-FABRIC-001`, `ADR-HERMES-CCO-WORKING-MEMORY-001`
**BL:** `BL-MWP-CANONICAL-EVIDENCE-LEDGER-001`

## Context

The system spans Hermes Desktop/GPT Luna, Hermes runtime, MemoryManager, Cortex/world-model, agents, Git, graph, Qdrant/GNN, Obsidian and reconciliation daemons. Health endpoints and declarations alone do not prove that a lifecycle transition happened, was authorized, reached its target or can be rolled back. A prior runtime-route regression demonstrated that a fix can disappear at image/recreate boundaries unless source, deployment and runtime evidence are correlated.

## Decision

MWP uses one canonical metadata-only evidence ledger for governed lifecycle transitions. Every event must be attributable, scoped and terminally classified.

```text
intent
→ pre-read
→ authority/lease
→ execute
→ receipt
→ destination read-after-write
→ projection receipt
→ effect/measure
→ promotion or rollback
```

```text
source pre-read/hash
→ MWP/CAD/ADR/BL governance preflight
→ lease
→ scoped Git commit
→ artifact/image build + hash
→ test + compile
→ deploy/restart
→ source/container hash parity
→ route/health readback
→ graph receipt/read-after-write
→ Obsidian projection/readback
→ rollback receipt if any gate fails
```

A build is not complete because an image built or a container is healthy. Source/image/runtime parity and downstream receipts are mandatory.

```text
turn_start
turn_complete
turn_timeout
turn_abort
build_job_open
build_source_preread
build_source_hash
build_governance_preflight
build_lease_acquire
build_scoped_commit
build_artifact_build
build_artifact_hash
build_test
build_compile
build_deploy
build_restart
build_runtime_source_hash
build_container_hash
build_route_readback
build_health_readback
build_graph_receipt
build_graph_read_after_write
build_obsidian_projection
build_obsidian_readback
build_rollback
identity_resolve
role_provider_select
memory_prefetch
memory_recall
memory_use
memory_effect
memory_promote
memory_rollback
lease_acquire
lease_heartbeat
lease_expire
workflow_preflight
scoped_commit
remote_readback
graph_write
 graph_read_after_write
obsidian_projection
obsidian_readback
reconciler_attempt
reconciler_retry
reconciler_dead_letter
drift_detected
deployment_source_hash
deployment_runtime_hash
health_transition
```

## Required receipt envelope

```text
receipt_id
event_id
parent_event_id
correlation_id
causation_id
recorded_at
freshness_seconds
principal_id
tenant_id
system_scope
surface_id
device_id
session_id
conversation_id
role_id
agent_id
provider_ref
declared_model_ref
selected_model_ref
memory_layer_id
canonical_authority_ref
lease_ref
operation
target
source_ref
content_hash
source_hash
runtime_hash
status
error_class
retry_count
read_after_write
runtime_effect_ref
rollback_ref
provenance_ref
```

Raw prompts, private memory payloads, credentials, tokens and secrets are prohibited. A receipt may contain hashes, identifiers and bounded error metadata only.

## Status semantics

```text
DECLARED
STARTED
RUNNING
ALLOWED
APPLIED
READ_AFTER_WRITE_VERIFIED
COMPLETED
DEFERRED
TURN_TIMEOUT
ABORTED
RETRYING
DEAD_LETTER
ROLLED_BACK
BLOCKED
```

`HEALTHY`, `200` or `RUNNING` never imply `COMPLETED`.

## Authority and retention

The ledger is append-only from runtime surfaces; canonical promotion and correction remain MWP-governed. Every projection has its own receipt. Missing receipt, stale freshness, hash mismatch, principal mismatch or target mismatch fails closed and raises drift.

## Acceptance boundary

This ADR is not runtime-complete until a live canary proves one complete receipt chain across Hermes/GPT Luna, MemoryManager, Cortex, Git, graph and Obsidian, including timeout, retry, read-after-write and rollback behavior.
