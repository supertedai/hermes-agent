# MWP-UOSH — Theory/Cosmos/EFC/ASI OS domain-home contract

**Status:** `DECLARED / STEWARD PROPOSAL / RUNTIME GATED`  
**Owner:** Morten  
**Home class:** `H10 — Theory, Cosmos, Consciousness & ASI OS`  
**Primary source:** `https://github.com/supertedai/EFC`  
**Public source surface:** `https://github.com/supertedai/EFC/tree/main/docs/public`

## 1. Architectural placement

This is not a company tenant and not a generic Opus infrastructure service. It is a Morten-owned theory/research and meta-architecture domain that is implemented through Symbiose, the graph, EFC source/papers and Opus/ASI system design.

```text
Morten / Theory & Cosmos
└── H10 — EFC · EBE · RCMP · Consciousness · ASI OS
    ├── EFC — Energy-Flow Cosmology
    ├── EBE — Entropy-Bounded Empiricism
    ├── S0/S1 ontology and entropy balance
    ├── L0–L3 regime architecture
    ├── RCMP — Regime-Consistent Measurement Principle
    ├── EFC meta-/cosmos model
    ├── consciousness / autopoiesis / cognition interfaces
    ├── ASI OS architecture
    ├── ASI map / capability topology
    ├── Symbiose graph/world-model projections
    └── public research artefacts and validation ledgers
```

The domain is authored/owned by Morten, stewarded through Opus, and must remain semantically distinct from:

- Morten's personal LifeContract domains;
- Opus internal operational domains such as Cyber;
- Company tenants;
- external scientific sources and third-party evidence.

## 2. Canonical domain and tenant

```yaml
tenant_id: morten:theory-cosmos
home_class: H10
domain_id: theory.cosmos.efc-asi
owner_principal: morten
system_operator: opus
primary_steward_proposal:
  agent_id: efc-asi-steward
  role: theory-cosmos-asi-steward
  status: PROPOSED_NOT_LIVE_VERIFIED
```

The proposed steward is one bounded primary steward at first. It may later delegate bounded lanes, but those lanes must retain the same provenance and owner boundary:

```text
EFC/EBE/RCMP lane
Consciousness/meta-model lane
ASI OS/ASI map lane
Graph/Symbiose projection lane
Public artifact/validation lane
```

No existing registry entry is promoted to this role merely because it has a similar name or research skill. The agent binding requires a separate runtime and authority readback.

## 3. Steward mission

The EFC/ASI steward is responsible for maintaining coherence across:

- theory definitions and ontology;
- entropy balance and S0/S1 distinctions;
- EBE validity boundaries;
- RCMP regime-consistent measurement;
- L0–L3 regime architecture;
- EFC equations, predictions and falsification/kill criteria;
- consciousness, autopoiesis and cognitive interface models;
- ASI OS architecture and ASI capability maps;
- Symbiose graph/world-model representations;
- EFC paper packages, schemas and machine-readable manifests;
- public research artefacts, validation ledgers and changelog consistency.

The steward maintains coherence and proposes changes. It does not silently turn hypotheses into facts, empirical consistency into confirmation, or draft architecture into live capability.

## 4. Source layers

The steward must preserve the EFC repository's evidence separation:

```text
Layer 1 — EFC publications / own Figshare DOIs
Layer 2 — third-party external publications
Layer 3 — EFC working notes confronting external evidence
```

The following repository surfaces are authoritative for their respective purposes:

| Surface | Role | Default authority |
|---|---|---|
| `docs/public/` | public published face, ledgers, master specification, roadmap, figures | validate-then-publish source |
| `docs/papers/efc/` | AI-friendly paper packages, schemas, code and evidence packages | package/source authority |
| `docs/notes/` | internal specifications and test definitions | internal intent/specification |
| `pipelines/` | numerical generation and figures | computational source |
| `shared/configs/` | parameter/config source for pipelines | configuration authority |
| `figshare/` | DOI/deposit metadata | publication/provenance authority |
| `https://figshare.com/authors/Morten_Magnusson/20477774` | Morten's Figshare author/deposit profile | publication/deposit provenance; not claim validity by itself |
| `https://energyflow-cosmology.com/` | public programme narrative, concepts, resources, domains and outreach | public narrative/reference surface; not empirical evidence authority |
| `https://www.magnusson.as/` | Morten's authorial EFC surface: structural, dynamical, cognitive, principles, documentation and cooperation pages | authorial programme/reference surface; not sole identity, evidence or graph authority |
| `https://orcid.org/0009-0002-4860-5095` | Morten's persistent scholarly identity | author identity/provenance authority; not claim/evidence authority |
| Symbiose/graph | typed projections and relations | graph authority only when write/readback is verified |

`docs/public/` must not be edited as an unvalidated convenience surface. Public changes require upstream regeneration, validation and the repository's maintenance/CI gates.

## 5. Core conceptual model

The steward must preserve the distinction between:

```text
S0 = total space of possible structures/dynamics
S1 = realized universe/system
EBE = validity boundary for inference within S1
L0 = latent
L1 = stable active
L2 = complex active
L3 = residual/preserved structure
EFC = physical implementation in cosmological domain
RCMP = regime-consistent measurement methodology
ASI OS = operational/system architecture using the validity constraints
```

The steward must not collapse ontology, epistemology, regime dynamics, physical theory, cognition theory and operational ASI architecture into one undifferentiated claim layer.

## 6. Graph and Symbiose relationship

The domain may project typed entities and relations into Symbiose/graph, for example:

```text
TheoryClaim
Concept
Definition
Equation
Prediction
KillCriterion
Regime
EvidenceItem
PaperPackage
ValidationRun
ASIComponent
Capability
ArchitectureDecision
Projection
```

Every graph projection must carry:

```text
source_repo
source_path
source_commit_or_version
source_layer
claim_status
epistemic_level
regime_scope
provenance
freshness
owner_principal
steward_agent
readback_status
rollback_ref
```

A graph projection is not automatically a fact, memory, capability or runtime authority. Graph write remains blocked until authenticated writer identity and read-after-write evidence exist.

## 7. Public update authority

The steward may:

- scan repository drift;
- propose documentation changes;
- update internal manifests through the sanctioned workflow;
- run maintenance and validation checks;
- generate review artifacts;
- prepare public-doc patches;
- update graph projections when the canonical writer and gate are live.

The steward may not autonomously:

- publish unvalidated public claims;
- alter validation status from Planned/Awaiting to PASS;
- turn `consistent with` into `confirms`;
- add third-party evidence to EFC's own empirical registers;
- declare a sealed prediction successful without its criterion;
- promote a theory hypothesis to an authoritative fact;
- grant itself ASI capability or runtime authority;
- write graph/Obsidian state without authenticated Morten authority and read-after-write receipt.

## 8. Surfaces and navigation

This domain gets a canonical MWP home, with projections rather than one flat tab:

```text
H10 Theory/Cosmos canonical home
├── MWP/CAD architecture view
├── 01 · STYRING & SELV → ASI OS / architecture intent
├── 02 · KOGNISJON & LÆRING → consciousness / cognition / learning interfaces
├── 03 · SANNHET & INTEGRITET → EBE / RCMP / validation / provenance
├── 04 · DRIFT & OVERVÅKNING → pipeline health / maintenance / publication gates
├── 05 · VERDEN & DOMENER → EFC / Cosmos domain projections
├── Opus System → ASI map / capability topology (projection only)
└── Public EFC → docs/public artefacts and ledgers
```

The same concept may appear in several surfaces, but the canonical owner remains `morten:theory-cosmos`.

## 9. Gates

Before the domain is `MAPPED_LIVE`, MWP requires:

- canonical H10 domain record;
- dedicated steward-agent binding with `agent_binding_key`;
- Morten owner/authority readback;
- source repository and public-surface provenance;
- graph projection schema and claim-status mapping;
- public validate-then-publish workflow receipt;
- EFC maintenance/drift checks;
- rollback/version references;
- explicit separation of theory, evidence, hypothesis, prediction and runtime capability.

Current status:

```yaml
home: DECLARED
owner: VERIFIED_AS_REQUESTED_NOT_RUNTIME_READBACK
steward: PROPOSED_NOT_LIVE_VERIFIED
runtime: BLOCKED_UNTIL_STEWARD_READBACK
graph_write: BLOCKED_UNTIL_AUTHORITY_READBACK
public_publish: GATED_BY_EFC_VALIDATION_AND_CI
asi_authority: NOT_GRANTED
```

## 10. First permitted action

Run a metadata-only H10 reconciliation over:

1. EFC repository root and `AGENTS.md`;
2. `docs/public/`;
3. `docs/papers/efc/`;
4. RCMP package;
5. EBE/S0/S1/L0–L3 and consciousness/meta packages;
6. ASI OS and ASI map references in Symbiose/MWP;
7. current graph projections and source/provenance links.

Return one `TheoryHomeRecord` per package/domain with owner, source layer, claim status, steward scope, public-surface impact, graph projection status and next action. Do not activate the proposed steward or write graph records from repository discovery alone.
