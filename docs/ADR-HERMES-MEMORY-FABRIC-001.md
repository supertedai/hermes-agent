# ADR-HERMES-MEMORY-FABRIC-001 — Hermes engine as the runtime memory waist

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED / LIVE_CANARY_EVIDENCE`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `CAD-HERMES-MEMORY-FABRIC-001`

## Context

The system has three memory planes: chat/session, Opus/Cortex and agent/steward memory. Hermes already provides the mature agent engine, turn lifecycle, context handling, tool execution and delegation behavior. Building a second orchestration engine would create duplicate routing, inconsistent context and competing authority.

## Decision

All runtime memory interactions are routed through the existing Hermes engine and its MemoryProvider contract. The Holographic API is a compatibility/semantic contract, not a second canonical store or engine.

```text
Hermes engine = runtime orchestration and execution authority for a turn
MWP          = governance, identity, scope, provenance and mutation gates
Memory Fabric = durable canonical datatype stores and projections
```

Canonical authority is assigned per datatype, not globally to every surface:

- raw chat/session state: Hermes session authority;
- durable shared facts, learning and world-model entities: approved Memory Fabric authority;
- task/case/lease state: MWP task authority;
- vectors/FTS5/HRR/GNN: projections or rankers unless explicitly promoted;
- context/prefetch: Hermes runtime projection, never canonical truth.

## Consequences

Positive:

- preserves Hermes' existing engine instead of duplicating it;
- keeps prompt caching, turn ordering, tool execution and delegation in one path;
- allows Opus/Cortex and agent memory to evolve behind a stable provider contract;
- gives MWP one place to enforce scope and evidence around runtime use.

Required controls:

- adapter integration must use existing provider/plugin/service boundaries;
- no direct graph/vector writes from arbitrary model output;
- no global memory promotion from local Hermes state;
- degraded mode must be explicit and fail-closed;
- every projection must expose freshness, authority and provenance state.

## Rejected alternatives

1. A second Opus orchestration engine parallel to Hermes.
2. Making Hermes' local SQLite/FTS5 memory the durable shared authority.
3. Direct Hermes-to-Neo4j/Qdrant/GNN writes without MWP gates.
4. Injecting all 20 memory layers into every prompt.

## Holistic gap-gate decision

Every provider, schema, graph, vector, GNN, ingest, surface and learning change is reviewed as one cross-plane system against industry baseline, SOTA and ASI/cutting-edge criteria. The gate is fail-closed and requires live authority/provenance/read-after-write/rollback evidence before COMPLETE.

## Primary objective

The integration target is maximal cross-platform memory and learning coverage across Hermes chat/session, user, Cortex/system, agents/stewards, skills, tasks, evidence, graph/world-model, vector retrieval, structural ranking and evaluation. No single provider — including Holographic — is the target; providers are composable signal sources behind the Hermes lifecycle and MWP authority.

## Latency decision

Hermes local SQLite/FTS5 remains the hot-path latency baseline. Opus Memory Fabric integration must use bounded prefetch, cache and asynchronous enrichment so a slow graph/Qdrant/GNN backend cannot stall normal chat.

The adapter is not production-ready until benchmark evidence shows p50/p95/p99 retrieval and context-assembly latency, stale-hit rate, cache hit rate and async projection lag against the baseline. Until then, remote enrichment remains shadow/async and the local Hermes path is the safe fallback.

## Runtime memory UX decision

Hermes' normal turn path uses implicit engine lifecycle hooks for scoped prefetch, context assembly, turn capture and low-risk learning-event emission. The model/user must not be forced to call a memory tool for ordinary recall or capture.

Explicit memory tools are reserved for intentional inspection, explanation, correction, export and owner-gated mutation. This preserves Hermes' seamless chat behavior while MWP still governs durable promotion asynchronously and fail-closed.

## Shared backplane and learning consequence

The `.14` web GUI, PC/laptop Desktop clients and other Hermes surfaces are clients of one canonical backplane. They may expose different views, but they do not own separate durable memory or learning stores.

Hermes, Cortex and agents emit learning events through the canonical ingest envelope. Promotion is scoped to `system/platform`, `user`, `chat/session` or `agent/domain`; relevant projections are returned through Hermes. No learning event is broadcast globally merely because it was observed by one agent or surface.

## Acceptance boundary

Architecture is accepted. Runtime implementation is not accepted until BL-HERMES-MEMORY-FABRIC-001, BL-HERMES-INGEST-001, BL-HERMES-SURFACE-BACKPLANE-001 and BL-HERMES-LEARNING-LOOPS-001 provide live, scoped, metadata-only receipts and runtime-effect evidence.

## Addendum — selective adoption of Hindsight/Mnemosyne capabilities

**Decision status:** `PROPOSED / SHADOW-GATED`

We will adopt useful memory mechanisms from Hindsight and Mnemosyne selectively, behind the existing Hermes `MemoryProvider` lifecycle and MWP promotion contract. We will not install a parallel canonical memory system and will not treat provider presence as runtime authority.

The first candidate scope is:

- `retain → recall → reflect` lifecycle hooks;
- typed separation of facts, experiences, observations, hypotheses/opinions, decisions and procedures;
- temporal validity, supersession and contradiction metadata;
- duplicate/conflict classification before promotion;
- Honcho-like user-model candidates with owner/provenance review;
- a shadow evaluation harness against the local Hermes SQLite/FTS5 baseline.

Acceptance requires a real shadow receipt containing provider/config identity, principal/scope, candidate and recall identifiers, source/provenance, latency, freshness, evaluation result and rollback path. The integration remains non-canonical and non-authoritative until the existing BL gates additionally prove scoped read-after-write, failure/degraded behavior, no scope leakage and measurable runtime benefit. No claim is made here that Hindsight or Mnemosyne is currently active in the profile.

## Addendum — ASI-grade memory gaps

**Decision status:** `OPEN / IMPLEMENTATION-GATED`

The Memory Fabric is extended with the following ASI-grade requirements. These are acceptance targets, not claims of current runtime completion.

### Decision

Memory must be modelled as a typed, temporal, provenance-bearing and evaluable cognitive substrate. The canonical contract must cover:

- working, episodic, semantic, procedural, prospective, self-model, social/user and meta-memory;
- epistemic types such as observed fact, user assertion, derived observation, experience, hypothesis, opinion, decision and verified rule;
- lifecycle transitions for candidate, deduplicated, canonicalized, active, superseded, contradicted, quarantined, expired and deleted;
- active retrieval conditioned by semantics, time, graph, causality, contradiction, goals and uncertainty;
- causal records linking situation, action, expected effect, actual effect, hypothesis, confidence and evidence;
- capability/self-model memory with freshness and measured verification;
- security controls for principal, tenant, scope, sensitivity, consent, reader/writer policy and memory poisoning;
- correction, deletion, retention, audit and rollback;
- consolidation/compression that preserves provenance, uncertainty and source links;
- multi-timescale and multi-agent memory where shared candidates do not imply shared authority.

### Non-negotiable acceptance gate

No memory feature is considered runtime-effective from storage or endpoint presence alone. A live receipt must correlate:

```text
retain → recall → use in decision → measured effect
      → linked learning signal → promotion receipt → rollback
```

The current evidence is insufficient for this gate: retrieval/use/effect/promotion correlation is missing, and the existing synthetic transfer evaluation is explicitly not live agent-effect evidence. These lanes remain `BLOCKED` until metadata-only runtime receipts, scoped authority, provenance, read-after-write and rollback are demonstrated.
