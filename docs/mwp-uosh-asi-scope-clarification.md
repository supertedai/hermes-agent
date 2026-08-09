# MWP-UOSH-001 — ASI scope clarification

## Scope correction

`MWP-UOSH-001` is not primarily a Faber, coding or Desktop automation project. Those are capabilities and surfaces inside a larger ASI-oriented architecture.

The original objective is persistent, per-user memory and learning across everything the user says and does, extended across Opus/Hermes/Symbiose and all connected surfaces. Coding/Faber is a later capability extension of that system.

## Three orthogonal axes

### Axis 1 — Per-user plane

What the system knows and learns about a principal:

- 20 memory layers;
- user-scoped recall and gates;
- identity, role and capability;
- projects, domains and preferences;
- provenance, freshness, confidence and correction;
- user-owned sources and documents;
- user-specific learning and workflows.

Morten's original single-user owner/admin plane and Joakim's later authenticated multiuser plane must remain distinct.

### Axis 2 — System/Cortex world model

What the overall Opus/Symbiose system knows about its environment and itself:

- world model;
- entities, variables and relations;
- source registry and ingest lineage;
- graph/Qdrant/GNN projections;
- system state, topology and service health;
- hypotheses, causal/temporal/predictive relations;
- cross-agent synthesis under governance;
- global/system learning separated from private user memory.

### Axis 3 — Per-agent plane

What each agent/steward can perceive, remember, reason over and improve:

- agent identity and domain scope;
- agent-local memory and instances;
- steward-owned sources and workflows;
- agent cognition capabilities;
- goals, proposals, approvals, actions and outcomes;
- self-model, gaps, calibration and learning;
- controlled traversal to user and system planes.

Agent memory is not automatically user memory. A steward may provide reachability without proving user-level recall or promotion.

## Required loops

### Memory loop

```text
capture
→ source/provenance
→ ingest
→ layer classification
→ storage
→ reader/instance
→ scoped recall
→ correction/consolidation
→ promotion or tombstone
→ read-after-write
```

### Cognition loop

```text
sense
→ model/world-state
→ reason
→ set domain goal
→ learn from user/outcome
→ propose
→ approval gate
→ act
→ measure outcome
→ calibrate
→ loop
```

The final two stages are not optional: action requires approval where gated, and learning requires measured outcome rather than executor success.

## Surface contract

Every surface — Desktop, web, gateway, TUI, Faber, Opus and each steward — must expose or feed the same logical contracts:

- identity/principal;
- source/ingest;
- memory layer;
- world-model relation;
- agent context;
- learning event;
- workflow/proposal;
- approval/enactment;
- outcome/evidence;
- status/readback.

The UI may be metadata-only, but the backend must retain authoritative provenance and state.

## Ingest contract

Each surface/agent must have an explicit ingest path for its own inputs and sources:

```text
surface/agent
→ owner/principal
→ source registry
→ encrypted/storage policy
→ injection/secret scan
→ chunk/transform
→ graph/Qdrant/embedding projection
→ scoped memory/world-model destination
→ evidence/readback
```

Existing ingest systems must be reused and reconciled. The MWP must not create a second ingest universe.

## Existing UI interpretation

The supplied `/symbiose` and agent panels are evidence of an existing architecture:

- two memory counts (`own` versus `reachable via stewards`) are distinct and must not be summed;
- `blind`, `absent`, `unconnected` and `reachable` are different epistemic states;
- source ownership and agent reachability are separate;
- cognition capabilities and enactment gates are separate;
- proposed/approved/action/outcome must remain distinct.

The MWP should map and preserve these semantics, not flatten them into a single boolean or count.

## Consequence for implementation order

The control-plane and automation work follows the canonical critical path in `CAD-MWP-ASI-CRITICAL-PATH-001`:

```text
P0 baseline/topology/rollback
→ P1 auth/session/thread parity
→ P2 canonical CRUD/truth/authority
→ P3 Hermes ingest + four-plane memory
→ P4 learning-loop promotion/rollback
→ P5 Cortex/agent/Jetstream roundtrips
→ P6 surface parity and Desktop-front web migration
→ P7 graph/Qdrant/GNN/Obsidian governed writers
→ P8 bounded autonomy/ASI evaluation
```

Independent read-only and preflight work may run in parallel, but no dependent lane may be promoted ahead of its predecessor.

## Status

`SCOPE CLARIFIED / ARCHITECTURE REBASE REQUIRED`
