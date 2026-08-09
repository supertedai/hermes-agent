# MWP-UOSH-001 — Hermes ↔ Symbiose Memory/Learning Interoperability Proposal v1

**Status:** `SUPERSEDED_AS_ARCHITECTURE_BY_CAD-HERMES-MEMORY-FABRIC-001 / RUNTIME_NOT_VERIFIED`
**Canonical architecture:** `CAD-HERMES-MEMORY-FABRIC-001`
**Canonical decision:** `ADR-HERMES-MEMORY-FABRIC-001`
**Execution lane:** `BL-HERMES-MEMORY-FABRIC-001`
**Authority:** MWP-UOSH-001
**Scope:** Hermes/Opus intelligence and execution layer ↔ Symbiose canonical memory, learning and world-model substrate
**Mode:** Architecture proposal; no live writes, promotion, restart, schema mutation or writer change authorized

## 1. Problem statement

Hermes/Opus has conversation memory, working memory, skills, feedback and learning-candidate behavior. Symbiose has persistent, shared and provenance-bearing memory, graph/world-model state, vector projections and learning records. These surfaces must exchange state without creating two silently diverging authorities.

The target is a seamless and fast user experience in all directions while preserving identity, consent, provenance, freshness, conflict handling, rollback and canonical authority.

## 2. Core architectural decision proposed

Do **not** implement unrestricted symmetric CRUD between Hermes and Symbiose.

Implement **governed bidirectional interoperability** with asymmetric authority:

```text
Hermes/Opus
  = conversation/session memory, working memory, reasoning,
    feedback, observations, learning candidates and proposals

Symbiose
  = canonical persistent/shared memory, world model, provenance,
    cross-agent projections, consent/deletion authority and promotion state
```

Each datatype must have one canonical authority. Hermes may be the canonical writer for session-local working state; Symbiose is the canonical writer for durable shared state unless an explicit exception is approved.

## 3. Interoperability contract

### 3.1 Read path

```text
Hermes request
  → principal/profile/session/agent scoped retrieval
  → local/read-model cache where safe
  → Symbiose graph/vector/world-model sources
  → provenance/freshness/confidence envelope
  → Hermes context projection
```

Reads must expose at least:

- status and target runtime;
- identity and scope;
- source and writer;
- freshness and version;
- confidence and conflict state;
- evidence/provenance reference;
- whether the result is canonical, projected, cached, stale or unknown.

### 3.2 Write path

```text
Hermes observation/command
  → typed event or change proposal
  → outbox/idempotency key
  → identity, consent, policy and provenance validation
  → conflict/version gate
  → Symbiose canonical write or quarantine
  → read-after-write receipt
  → Hermes projection update/event
```

The write path must distinguish:

```text
local_pending
accepted_for_processing
canonical_write_confirmed
projected_back
conflicted
quarantined
rejected
rolled_back
```

### 3.3 CRUD mapping

| Operation | Hermes → Symbiose | Symbiose → Hermes |
|---|---|---|
| Create | Candidate memory, insight, learning signal, goal, feedback or event | Canonical facts, promoted learning and scoped context projections |
| Read | Scoped retrieval request | Canonical graph/vector/world-model response with provenance |
| Update | Versioned command/proposal; no blind overwrite | Updated projection, correction, stale/conflict signal |
| Delete | Consent-gated correction/retraction/tombstone request | Retraction/tombstone propagation to Hermes caches and working model |

Sensitive facts, identity, private memory, policy and deletion require stronger owner/consent gates than low-risk feedback or session-local state.

## 4. Learning promotion contract

No model-generated inference becomes canonical memory merely because Hermes produced it.

```text
observation
  → candidate
  → evaluated
  → reviewed
  → promoted
  → monitored
  → rolled_back (if required)
```

Every learning item must declare its target axis:

```text
user | agent | system | filtered_multi_projection
```

A promotion record must include source, writer, timestamp, scope, evidence, confidence, evaluation result, reviewer/owner gate and rollback reference.

## 5. Consistency and performance model

Use two service classes:

### Hot path

For normal chat retrieval, working memory, low-risk feedback and read models:

- local/projection cache where policy permits;
- Qdrant/graph read models kept warm;
- no GNN inference in the critical chat path unless explicitly required;
- bounded latency and freshness budgets;
- stale/degraded status surfaced rather than hidden.

### Governed path

For canonical learning, sensitive writes, deletes, promotions and conflict resolution:

- asynchronous event acceptance is allowed;
- canonical confirmation is separate from acceptance;
- read-after-write verification is mandatory;
- retries are idempotent;
- failures go to quarantine/dead-letter handling;
- rollback/tombstone behavior is explicit.

Required measurements:

```text
read latency
write acknowledgement latency
canonical promotion latency
freshness lag
read-after-write success
lost/duplicated event rate
conflict rate
quarantine rate
rollback success
retrieval precision/recall and stale-hit rate
```

HTTP health alone is not an acceptance criterion.

## 6. Reliability and governance requirements

The implementation should use:

- typed commands/events rather than raw free-text writes;
- correlation ID, causation ID and idempotency key;
- optimistic versioning or equivalent concurrency control;
- outbox/inbox or equivalent durable delivery;
- dead-letter/quarantine path;
- deterministic deduplication;
- W3C-PROV-compatible provenance fields where practical;
- principal, profile, session, agent and project/domain scope;
- consent and deletion/retraction semantics;
- correction events instead of silent mutation;
- audit trail and independently verifiable rollback refs;
- projection rebuild capability from canonical events/state.

## 7. MWP alignment

This proposal operationalizes existing MWP integration gaps and topology requirements:

- **G-02:** user memory ↔ agent memory ↔ system world model traversal;
- **G-03:** storage, reader/writer, scope, provenance, freshness, conflict and correction contract;
- **G-05:** cognition/event separation for observation, reasoning, learning, proposal, approval, action and outcome;
- **G-06:** candidate → evaluated → reviewed → promoted → monitored → rolled back;
- **G-07:** agent steward identity, memory instances, readers, writers, tools and outcome recorder;
- **G-08:** parity across Hermes Desktop, gateway, TUI, Faber and Symbiose surfaces;
- **G-13:** metadata-only status, scope, evidence, freshness, confidence, gate and next action;
- **Perfect topology contract:** ConversationWorkingModel ↔ OpusWorkingMemory ↔ principal-scoped Symbiose memory/learning/goals.

`CASE-SYMBIOSE-02` remains a graph/Qdrant/GNN integrity case. It does not by itself close this Hermes↔Symbiose interoperability proposal.

## 8. Acceptance criteria proposed

The proposal is not complete until all of the following have live evidence:

- canonical authority is declared for every memory/learning datatype;
- Hermes and Symbiose can perform scoped readback with provenance and freshness;
- typed create/update/delete/retraction paths are versioned and idempotent;
- read-after-write is verified for canonical writes;
- duplicate delivery does not duplicate state;
- conflicts are detected, surfaced and resolved through an owner/policy gate;
- learning promotion and rollback are independently verifiable;
- deletion/retraction propagates to projections and caches;
- hot-path latency and freshness budgets are measured;
- governed-path acknowledgement and canonical-confirmation latency are measured;
- graph, Qdrant and GNN projections are distinguishable from canonical source state;
- missing, stale, wrong-scope, rejected, quarantined and degraded states are tested;
- no parent MWP closeout occurs while this contract remains unverified or blocked without owner/evidence/next action.

## 9. Explicit non-goals

This proposal does not authorize:

- unrestricted bidirectional writes;
- direct model-driven canonical promotion;
- destructive graph or vector mutation;
- replacing Hermes working memory with a remote store;
- replacing Symbiose canonical persistence with Hermes local state;
- silent conflict resolution;
- treating GNN similarity as truth;
- claiming seamless runtime behavior before end-to-end measurement.

## 10. Next permitted action

Create a reviewed contract/test matrix for memory and learning datatypes, then perform metadata-only topology and route readback for the Hermes↔Symbiose paths. Implementation, writer changes, schema changes and promotion remain blocked until identity, owner, provenance, rollback and evidence gates are approved.
