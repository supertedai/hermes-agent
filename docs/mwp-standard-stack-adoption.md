# MWP-UOSH standard adoption

## Scope

This document adopts industry-standard contracts without creating parallel authority stores.
Existing MWP change ledger, graph authority, verification evidence, Kanban/task authority and
Hermes scheduler remain canonical.

## Adopted standards

| Standard | MWP role | Status |
|---|---|---|
| OpenTelemetry GenAI semantic conventions | model, agent, tool, retrieval and workflow telemetry | CONTRACT_ADOPTED; SDK installed in isolated MWP venv |
| W3C Trace Context | `traceparent`/`tracestate` propagation across Hermes/MWP/Faber/Halo | CONTRACT_ADOPTED |
| NIST AI RMF | Govern / Map / Measure / Manage mapping for every autonomous lane | CONTRACT_ADOPTED |
| ISO/IEC 42001 concepts | AI management-system controls, ownership, risk and continual improvement | POLICY_MAPPING |
| SLSA + in-toto | signed/attested source-to-artifact provenance | RECEIPT_CONTRACT; no production signer activated |
| MLflow-compatible run fields | parameters, code, metric, artifact and lineage tracking | MWP_SCHEMA; no second tracking store |
| OWASP LLM/agent security practices | least privilege, injection/secret gates, bounded tools and human approval | SECURITY_GATE_MAPPING |

## Runtime boundaries

- Halo is diagnostic only. Its output is `provenance=halo_self_report` and `verified=false` until independently checked.
- Autoresearch is an isolated experiment source under BL-3935. The canonical runtime is on `box12` (`/home/byopus/external/BL-3923/autoresearch`) via `/home/byopus/run_autoresearch_loop.sh`; the `.15` checkout is a non-authoritative development/shadow copy. It may not modify Hermes, MWP, graph authority or production code directly.
- OTel telemetry is metadata-only by default. Raw prompts, secrets, private payloads and chain-of-thought are excluded.
- Experiment promotion requires baseline, after metric, rollback reference, reviewer verdict and measured outcome.
- NIST `GOVERN`, `MAP`, `MEASURE`, `MANAGE` are represented in the workflow receipt; a green row count is not proof of substance.

## Required receipt chain

```text
Morten directive
→ BL/CAD/ADR scope
→ trace context
→ bounded experiment/worktree
→ baseline
→ change
→ tests
→ reviewer verdict
→ artifact provenance
→ runtime/readback
→ measured outcome
→ learning event/promotion
```

## Explicit non-goals

- No MLflow server or parallel experiment database.
- No automatic training on this host without GPU and an owner-approved run.
- No Halo executor role.
- No automatic SLSA signing key or credential creation.
- No production activation merely because a package or skill is installed.
