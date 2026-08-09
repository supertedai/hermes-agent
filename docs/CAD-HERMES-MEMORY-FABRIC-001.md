# CAD-HERMES-MEMORY-FABRIC-001 — Hermes-centred Memory Fabric

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED / LIVE_CANARY_EVIDENCE`
**Live closeout addendum:** `docs/mwp-live-governance-closeout-status-v1.md`
**Parent:** `MWP-UOSH-001`
**Authority:** MWP-UOSH authority
**Scope:** Chat/session, Hermes engine, Opus/Cortex, agent/steward memory, Memory Fabric and projections

## Decision

Hermes' existing agent engine is the mandatory orchestration and execution waist for all user-facing and agent-facing memory flows. We do not create a second orchestration engine beside Hermes.

```text
chat/channel/desktop/gateway
        ↓
Hermes agent engine  ← mandatory execution/orchestration path
        ↓
MemoryProvider contract
        ↓
Holographic/Opus adapter
        ↓
Opus Memory Fabric / canonical datatype authorities
        ↓
graph · vector · GNN · evidence projections
```

Hermes is the runtime consumer, context assembler, tool/agent orchestrator and lifecycle owner for a turn. It is not automatically the canonical owner of every durable memory datatype. Canonical authority remains datatype-scoped and governed by MWP.

## Three-plane model

| Plane | Canonical concerns | Hermes responsibility |
|---|---|---|
| Chat/session | raw transcript, conversation state, turn metadata | receive turn, preserve ordering, invoke provider, assemble context |
| System/Cortex | goals, self-model, world-model, learning state | route through engine, request scoped retrieval, execute approved handoff |
| Agent/steward | role/domain/task memory, capability and outcome context | bind agent, enforce scope, perform handoff and return result through engine |

A shared fact may project to more than one plane, but it has one canonical key/authority and explicit projection receipts.

## Mandatory holistic gap gate

Every MWP/CAD/ADR/BL implementation step must automatically evaluate industry baseline, SOTA, ASI/cutting-edge relevance, cross-plane compatibility, tests, live evidence and rollback. This is mandatory for schema, Neo4j, Qdrant, GNN, Hermes providers, ingest, CRUD, surfaces, learning and restore work.

The machine-readable protocol is:

```text
docs/mwp-holistic-automatic-gap-gate-v1.json
```

No step may be closed from local tests, inventory, schema declaration or provider presence alone.

## Implicit memory lifecycle requirement

Normal Hermes chat must not pause for model-visible memory/search/write tool calls. Memory retrieval, context prefetch, turn capture and low-risk learning-event emission belong inside the Hermes engine lifecycle and MemoryProvider boundary:

```text
turn start
  → implicit scoped prefetch
  → context assembly
  → model/tool/agent execution
  → implicit observation/feedback capture
  → governed async ingest/promotion
  → next-turn projection
```

Explicit memory tools remain available for user-initiated inspection, explanation, correction, export or owner-approved mutation. They are not the normal transport for Hermes' own memory operation.

## Primary objective: maximal cross-platform memory and learning

The objective is not to select Holographic or any single provider. The objective is to maximize useful memory, learning and retrieval potential across every Hermes surface and every Opus/Symbiose layer. Hermes remains the runtime waist; providers and projections are interchangeable capabilities behind the lifecycle boundary.

Coverage must include chat/session, user, system/Cortex, agents/stewards, skills, tasks/goals, evidence/provenance, graph/world model, vectors, structural ranking, evaluation/feedback and every authenticated platform/device surface.

A memory candidate should be able to move through:

```text
surface/turn
→ implicit capture/prefetch
→ scoped candidate + provenance
→ canonicalization/contradiction handling
→ governed promotion
→ graph/vector/ranking/context projections
→ feedback/evaluation/rollback
```

No provider is the goal. Holographic may contribute FTS5/trust/HRR semantics, while other providers or native Hermes stores may contribute other signals. The MWP design must compose the strongest verified signals without creating parallel canonical authorities.

## Hermes-native baseline versus Opus layers

The built-in Hermes baseline is not equivalent to the Opus/MWP architectural layer model. Hermes core provides built-in `MEMORY.md`/`USER.md`, SQLite session persistence/FTS5 session search, its learning loop and the provider lifecycle (background prefetch, context injection, post-response sync and optional session-end extraction). Holographic is an external provider/plugin with its own SQLite fact store, FTS5, trust scoring and HRR retrieval; those ranking/composition semantics must not be presented as native Hermes-core layers.

The Opus/MWP layer matrix remains useful as a governed projection model, but each layer requires live storage, authority, scope, provenance and runtime-effect evidence.

## Latency and seamlessness requirement

The Memory Fabric integration must not make Hermes chat slower than the current local SQLite/FTS5 memory path by an unbounded amount. The local Hermes path remains the hot-path baseline; graph/Qdrant/GNN and remote projections are bounded, cached or asynchronous.

```text
L0 current-turn context
L1 process/session cache
L2 local Hermes SQLite/FTS5 working memory
L3 remote Memory Fabric / graph / Qdrant
L4 GNN/deep reasoning enrichment
```

Rules:

- normal turn retrieval uses a bounded deadline and never waits indefinitely for L3/L4;
- cache keys include principal/tenant/scope/session and canonical version;
- stale cache is labelled and never crosses scope boundaries;
- remote enrichment may arrive asynchronously for a later turn;
- writes and learning promotion use an outbox/async path, not the synchronous chat critical path;
- degraded mode falls back to safe local/read-only context and reports freshness state;
- no cache may become an untracked competing writer.

Acceptance requires measured p50/p95/p99 latency and freshness against the current Hermes SQLite/FTS5 baseline. If the adapter cannot meet the agreed budget, it remains shadow/async and Hermes local memory stays authoritative for the hot path.

## Non-negotiable invariants

1. No chat, Cortex or agent memory path bypasses the Hermes engine for runtime execution.
2. Hermes local session memory/cache is not silently promoted to shared canonical truth.
3. Graph, Qdrant, GNN, FTS5 and HRR are projections/indexes/rankers unless an explicit MWP datatype authority says otherwise.
4. Every retrieval and handoff carries principal, tenant, system scope, session/conversation, agent and provenance metadata.
5. Every canonical mutation is idempotent, versioned, receipt-bearing and read-after-write verified.
6. Model-generated inference remains a candidate until evaluation/owner/promotion gates close.
7. Prompt/context projection is scoped and ranked; the 20 memory layers are never blindly injected as raw prompt blocks.
8. Provider/backend failure degrades to explicit read-only or unavailable status; it never silently falls back to an unscoped writer.
9. Hermes normal chat memory retrieval/capture is implicit at engine/MemoryProvider lifecycle; explicit tools are not a latency dependency.

## Runtime roundtrips

Required paths:

```text
Chat → Hermes engine → scoped memory → Cortex
Chat → Hermes engine → scoped memory → agent
Agent → Hermes engine → Cortex/world-model proposal
Cortex → Hermes engine → scoped agent handoff
Memory Fabric → Hermes engine → context projection → turn
```

The architecture is not runtime-complete until each path has a metadata-only receipt and a real runtime-effect measurement.

## Shared surface/backplane rule

Web GUI on `.14`, Hermes Desktop on PC/laptop and other channels are surfaces, not competing memory authorities. They all use the same canonical auth/session and backplane route:

```text
surface (`.14` web / PC / laptop / gateway)
  → canonical auth + session
  → Hermes engine
  → canonical ingest/backplane
  → Memory Fabric / Cortex / agent projections
```

Each installation/device carries explicit `installation_id`, `device_id`, `login_surface_id`, `principal_id`, `tenant_id` and `session_id`. A surface must never create a second unscoped memory or learning writer.

## Learning projection rule

Hermes learning, Opus/Cortex learning and agent learning all emit governed events through the ingest envelope. They are projected by scope:

```text
system/platform | user | chat/session | agent/domain
```

Shared backplane does not mean global broadcast. Every promotion and projection retains owner, scope, provenance, freshness, evaluation and rollback metadata.

## Status boundary

This CAD records the architecture and implementation gates. It does not claim live Opus binding, graph authority, Cortex roundtrip, agent projection, `.14` backplane parity or Hermes provider activation. Those remain `OPEN`, `UNVERIFIED` or `BLOCKED` until live receipts exist.

## Capability adoption: Hindsight/Mnemosyne patterns

**Status:** `PROPOSED / SHADOW-GATED`

The Memory Fabric should evaluate and, where beneficial, adopt the strongest verified capabilities from Hindsight and Mnemosyne without introducing a second canonical memory authority or replacing the Hermes runtime waist.

Target capabilities:

1. **Explicit memory lifecycle:** `retain → recall → reflect` for automatic capture, scoped retrieval and reflective consolidation.
2. **Typed memory networks:** separate world facts, experience, observations, hypotheses/opinions, decisions and procedures rather than treating all durable memory as one undifferentiated fact class.
3. **User-model proposals:** Honcho-like modelling of user style and preferences, emitted as provenance-bearing candidates and never silently overwriting the canonical user profile.
4. **Temporal lifecycle:** `observed_at`, `valid_from`, `valid_until`, `supersedes`, `contradicts`, confidence and freshness.
5. **Conflict and duplicate handling:** classify new candidates as duplicate, update, supersede, contradict or quarantine before promotion.
6. **Retrieval evaluation:** measure recall precision/coverage, stale-hit rate, irrelevant injection, latency, token cost and scope leakage against the Hermes local SQLite/FTS5 baseline.

Adoption rule:

```text
Hindsight/Mnemosyne capability
  → adapter or native Opus implementation
  → shadow candidate/recall output
  → scoped provenance + evaluation
  → owner/promotion gate
  → canonical datatype authority
```

No third-party provider may write directly to graph, vector, user-profile, skill or runtime-authority stores. A real provider integration remains `SHADOW/ASYNC` until live read-after-write, rollback, latency, provenance and runtime-effect receipts exist. The current Opus provider remains the declared profile provider; this CAD change does not activate Hindsight or Mnemosyne.

## ASI-grade memory gap and acceptance contract

**Status:** `OPEN / IMPLEMENTATION-GATED`

The Memory Fabric must evolve beyond storage and similarity retrieval into a verifiable cognitive substrate for ASI-oriented operation. The following capabilities are mandatory design targets; declaration alone is not closure.

### Required memory classes

The canonical schema must distinguish at minimum:

```text
working | episodic | semantic | procedural | prospective
self-model | social/user | meta-memory
```

Memory content must also carry epistemic type, including `observed_fact`, `user_assertion`, `derived_observation`, `agent_experience`, `hypothesis`, `opinion`, `decision` and `verified_rule`. Epistemic type is not interchangeable with authority.

### Required lifecycle

Every durable memory candidate must support:

```text
candidate → deduplicated → canonicalized → active
         → superseded | contradicted | quarantined | expired | deleted
```

Required lifecycle metadata includes `created_at`, `observed_at`, `valid_from`, `valid_until`, `last_confirmed_at`, `supersedes`, `contradicts`, confidence, source, authority, scope, retention class and deletion status.

### Required ASI capabilities

1. **Active retrieval:** semantic, temporal, graph, causal, contradiction-, goal- and uncertainty-conditioned retrieval.
2. **Causal memory:** situation → action → expected effect → actual effect → causal hypothesis → confidence/evidence.
3. **Self/capability memory:** measured tool, agent, provider and workflow capabilities with freshness, failure history and verification evidence.
4. **Security and anti-poisoning:** principal/tenant/scope isolation, sensitivity, consent, reader/writer policy and treatment of recalled content as data rather than instructions.
5. **Forgetting and correction:** retention, deletion, quarantine, correction, audit and rollback without losing the provenance of what was previously used.
6. **Consolidation and compression:** derive stable patterns from episodes while preserving source links, uncertainty, temporal boundaries and contradiction history.
7. **Multi-timescale and multi-agent operation:** separate short-lived working context, episodic history and durable knowledge; share candidates across agents without silently sharing authority.

### Mandatory causal-effect gate

Runtime memory is not effective merely because a record exists or an endpoint returns data. Acceptance requires correlation of:

```text
memory retained
→ memory recalled
→ memory used in a decision
→ outcome/effect measured
→ learning signal linked
→ promotion receipt issued
→ rollback demonstrated
```

The existing live readback currently reports missing retrieval/use/effect/promotion correlation and therefore remains `BLOCKED` for promotion. Synthetic shadow evaluation is useful but is not live agent-effect evidence.
