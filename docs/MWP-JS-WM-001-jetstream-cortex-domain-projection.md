# MWP-JS-WM-001 — Jetstream → World Model → Cortex → Domain projection

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`
**Related:** `CAD-HERMES-INGEST-001`, `CAD-HERMES-LEARNING-LOOPS-001`
**Existing sources:** `tools/jetstream_scout.py`, `tools/world_model_hub.py`, `tools/worldmodel_gap_emitter.py`, `tools/jetstream_steward.py`

## Target flow

```text
Jetstream registry/feed
  → Hermes engine
  → canonical ingest envelope
  → source/provenance/injection checks
  → entropy + freshness + KnowledgeGap classification
  → canonical world_model_hub
  → Cortex/system projection
  → scoped agent/domain projections
  → optional learning candidate
```

Cortex receives the canonical system-level projection. Agents/domains receive a
scoped projection only when the signal is high-entropy or has relevant gap refs.
Raw payloads are not broadcast; projections carry refs, provenance, freshness,
confidence and scope.

## Routing rules

```text
fresh + injection-checked + high entropy/gap
  → Cortex + relevant domain agents
fresh + no trigger
  → Cortex only
stale
  → DROP_STALE
missing provenance/injection check
  → QUARANTINE
```

## Authority

- Jetstream registry/scout remains source-discovery authority.
- `world_model_hub` remains canonical world-model writer.
- Cortex receives the system projection; it does not become a second source.
- Domain agents receive scoped read/projection views, not global raw feed.
- Promotion into memory, graph, skill, workflow or runtime remains separately gated.
