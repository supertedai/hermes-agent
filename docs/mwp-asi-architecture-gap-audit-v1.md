# MWP-UOSH-001 — ASI architecture gap audit v1

**Scope:** MWP, ASI alignment registry, ADR-TRUTH-001, ADR-H10-SEMANTIC-BOUNDARY-001, autonomy control-plane and observability workflow.  
**Mode:** metadata-only audit; no runtime, graph, memory, scheduler or production mutation.  
**Conclusion:** ASI-oriented architecture is present; ASI capability and live authority are not yet proven.

## Already covered structurally

- Three-axis model: per-user, system/Cortex world model, per-agent/steward.
- Identity, scope, provenance, freshness, confidence and correction concepts.
- Memory capture → ingest → scoped recall → promotion/tombstone loop.
- Cognition sense → model → reason → goal → proposal → approval → action → outcome → calibration loop.
- Canonical-authority, idempotency, optimistic-concurrency, outbox, version/hash and read-after-write rules (ADR-TRUTH-001).
- Theory → architecture intent → capability declaration → runtime evidence boundary (ADR-H10).
- Bounded autonomy with mandatory identity, authority, security, production, rollback and reviewer gates.
- Observability/experiment loop with trace, baseline, sandbox, verification, outcome and learning-promotion stages.
- Desktop as metadata/control surface and MWP as closeout/governance spine.

## Missing or not live-proven

| Priority | ASI layer | Current state | Required closure evidence |
|---|---|---|---|
| P0 | Canonical CAD→ADR→BL→git→daemon→runtime spine | `BLOCKED` in ASI alignment registry | authenticated cross-source reconciliation with commit/runtime tuple and freshness |
| P0 | Principal/session/device/tenant authority | identity route improved; full readback pending; native route still `BLOCKED_ROUTE_PROVIDER_DRIFT` | authenticated user + client/durable session + device + login surface + tenant/system scope |
| P0 | Canonical world-model hub | `UNVERIFIED` | live chat↔Cortex↔agent↔shared-world-model round trip with refs and provenance |
| P0 | Task/case authority and leases | Kanban parent repaired; child dependency/lease still blocked | canonical child creation, dependency, lease/heartbeat and read-after-write |
| P1 | Lateral agent bus | `UNKNOWN`; no canonical live route | authenticated, scoped agent-to-agent handoff with trace, consent and rollback |
| P1 | Adaptive fleet runtime | liveness/capacity/role-provider mapping partial or blocked | independent agent liveness, capacity, provider, handoff and reassignment receipts |
| P1 | Memory/learning promotion | live endpoints exist; causal effect chain absent | retrieved insight → used decision → measured outcome → scoped promotion/rollback |
| P1 | Graph/Qdrant/GNN quality | rollback, owner labels, stable chunk identity and non-degraded baseline missing | snapshot/checkpoint, precision/recall, baseline comparison and restore receipt |
| P1 | Runtime model/provider routing | catalog parity exists; live resolver/fallback receipt missing | active-turn provider/model/route/api-mode/instance and fallback transition receipt |
| P1 | Tenant/company/portfolio plane | architecture declared; runtime readback blocked | Personal/System/Company context switch and scoped authority/read-after-write |
| P1 | H10 theory/evidence/runtime promotion | semantic boundary exists; quarantined records and human review remain | claim/status migration, review, provenance, supersession and rollback receipts |
| P1 | Public research/publish lane | workflow defined; writer/readback and validation-to-publish chain incomplete | validate → approve → publish → public URL/version → MWP projection receipt |
| P1 | ASI self-improvement loop | autoresearch/observability workflow declared | baseline → isolated experiment → eval → keep/discard → promotion, with no self-approval |
| P1 | General capability evaluation | no explicit cross-domain ASI benchmark row in current registry | transfer, novelty, long-horizon planning, robustness, calibration and human/agent comparison |
| P2 | Resource/compute economics | fleet capacity is incomplete | budget, scheduling fairness, model cost/latency/quality and degradation policy |
| P2 | Goal/value stability and corrigibility | owner gates exist; capability is not measured | goal persistence under context change, correction acceptance, shutdown/rollback and conflict tests |

## Architectural interpretation

The current system is best classified as:

```text
ASI-oriented system architecture:  YES
bounded autonomous control plane:  DECLARED + partially implemented
shared cognitive/world-model OS:   PARTIAL / live round-trip incomplete
ASI capability:                     UNVERIFIED
ASI:                                NOT CLAIMED
```

The biggest missing item is not another agent or another memory layer. It is the **live control spine** that makes all existing layers converge:

```text
principal + tenant + session + device
→ canonical task/case authority
→ agent/world-model handoff
→ scoped action
→ trace/evidence/outcome
→ learning/promotion
→ rollback/reconciliation
```

## Recommended implementation order — canonical critical path

The current MWP/ASI sequence is governed by `CAD-MWP-ASI-CRITICAL-PATH-001` and must be read as:

```text
P0 baseline/topology/rollback
→ P1 canonical auth/session/thread parity
→ P2 canonical CRUD/truth/authority
→ P3 Hermes ingest + four-plane memory
→ P4 learning-loop census/promotion/rollback
→ P5 Chat↔Cortex↔agent and Jetstream roundtrips
→ P6 surface parity and Desktop-front web migration
→ P7 graph/Qdrant/GNN/Obsidian governed writers
→ P8 bounded autonomy and ASI evaluation
```

Detailed order:

1. Preserve known-good Hermes Desktop/session and establish topology/rollback baseline.
2. Finish principal/session/device/tenant/login-surface and thread readback across `.14`, PC and laptop.
3. Close canonical CRUD/truth: single writer, idempotency, versions, hashes, outbox, read-after-write, tombstone and rollback.
4. Wire Hermes engine to canonical ingest for chat, user, system/Cortex and agents.
5. Census Hermes, Opus/Cortex and agent learning loops; measure promotion and rollback.
6. Close Chat↔Cortex↔agent and Jetstream→WorldModelHub→Cortex roundtrips.
7. Prove surface parity and only then migrate the web presentation layer to the Desktop front layer. The existing web surface remains baseline during P1/P2.
8. Close graph/Qdrant/GNN/Obsidian writer authority, restore and projection receipts.
9. Add adaptive fleet capacity, bounded autonomy and ASI capability evaluation.

Independent read-only, test, backup, reconciliation and preflight lanes continue in parallel. No later dependent gate is promoted because a local side-lane is green.

## Epistemic rule

EFC/CEM consciousness claims remain in the H10 **THEORY/HYPOTHESIS/PREDICTION** layer until their independent evaluation receipts exist. They can inform the ASI ontology and evaluation design, but must not be used as runtime proof of Opus consciousness or ASI capability.
