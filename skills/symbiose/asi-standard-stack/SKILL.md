---
name: asi-standard-stack
description: Use when designing or reviewing autonomous AI workflows; map them to OTel, W3C trace, NIST AI RMF, provenance and security gates.
---

# ASI standard stack

Use the existing MWP authority. Do not create a parallel task, memory, graph or experiment store.

## Required mapping

- `GOVERN`: BL/CAD/ADR, owner, reviewer, approval and rollback.
- `MAP`: axis (`user|system|agent`), principal, agent, scope and affected surfaces.
- `MEASURE`: baseline, OTel metadata, latency/cost/status and outcome.
- `MANAGE`: BLOCK/ESCALATE/KEEP/DISCARD, rollback and promotion.

## Trace

Propagate W3C `traceparent`/`tracestate`. Use OpenTelemetry GenAI semantic fields for model,
agent, tool and retrieval spans. Never emit secrets, raw private payloads or chain-of-thought.

## Provenance

Every experiment or code change needs source commit/config, worktree, trace, tests, reviewer,
artifact and runtime/readback references. SLSA/in-toto are provenance contracts, not permission
to sign or deploy automatically.

## Fail closed

- Halo output is diagnostic self-report until independently verified.
- Autoresearch is isolated and cannot directly modify production or MWP authority.
- Executor success is not measured outcome.
- Missing evidence stays OPEN/BLOCKED; it does not become PASS.
