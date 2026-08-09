# H10 v2 — EFC/ASI theory-domain lane taxonomy

**Status:** `DECLARED / TAXONOMY INTENT / REVIEW REQUIRED`  
**Home:** `morten:theory-cosmos / theory.cosmos.efc-asi / H10`  
**Primary steward proposal:** `efc-asi-steward` (`PROPOSED_NOT_LIVE_VERIFIED`)

## Design rule

H10 is one Morten-owned theory/programme domain, but it is not one undifferentiated lane. The lanes below separate identity, public narrative, ontology, physical theory, epistemology, method, evidence, cognition, AI architecture, computation and publication governance.

A package may have multiple **derived projections**, but it must have one canonical home lane and one source/provenance authority. No lane grants graph-write, public-publish or ASI-runtime authority by itself.

## Canonical lanes

| Lane | Canonical scope | Primary source authority | Steward responsibility | Forbidden conflation |
|---|---|---|---|---|
| **H10.0 Author identity & provenance** | Morten, ORCID, author/citation identity, affiliation | ORCID `0009-0002-4860-5095` plus signed/citation metadata | identity/provenance linking only | ORCID does not validate a scientific claim |
| **H10.1 Programme narrative & public concepts** | energyflow-cosmology.com, public concepts, resources, explanatory pages | `https://energyflow-cosmology.com/` | keep public narrative linked to canonical sources | website narrative is not empirical evidence |
| **H10.2 Ontology & foundations** | S0/S1, ontology, fundamental terms, grid/structure assumptions, foundational definitions | EFC master specification and ontology packages | definition/version/supersession control | ontology is not observation or runtime |
| **H10.3 Physical EFC model & cosmology** | EFC-S/EFC-D/EFC-C physical model, equations, energy flow, entropy gradients, cosmological regimes | Master Specification, theory packages, source equations | model coherence and notation | equations are not validation verdicts |
| **H10.4 EBE & regime architecture** | Entropy-Bounded Empiricism, S→0/S→1 bounds, L0–L3, regime transitions and validity boundaries | EBE and L0–L3 packages | epistemic boundary and regime tagging | validity protocol is not a claim that EFC is true |
| **H10.5 Measurement & comparison methodology** | RCMP, regime-locked measurement, likelihood, model comparison, uncertainty propagation, proxy placement | RCMP packages, likelihood/model-comparison ledgers | method versioning and test-design integrity | methodology is not result/evidence |
| **H10.6 Empirical validation, predictions & falsification** | validation ledger, predictions, sealed predictions, kill criteria, external comparisons, Stage-IV roadmap | `docs/public/EFC_Validation_Ledger.html`, `EFC_Predictions.html`, roadmap, DOI evidence register | claim/evidence/prediction status, no claim inflation | external consistency is not confirmation |
| **H10.7 Consciousness, cognition & meta-models** | EFC-C, CEM, cognitive entropy, consciousness bridge, autopoiesis, Homo Fluxus, mind/entropy interfaces | dedicated paper packages and meta/cognitive references | keep speculative/model/empirical levels distinct | consciousness model is not clinical or runtime consciousness evidence |
| **H10.8 Symbiosis & structural intelligence** | Human–AI co-reflection, graph-vector memory, long-horizon reasoning, validity-aware AI | Symbiosis/VAAI packages and architecture statements | architecture/projection semantics and safety boundaries | architecture intent is not live Opus capability |
| **H10.9 ASI OS & ASI map** | ASI OS, capability topology, agent/role architecture, control-plane concepts, maps and roadmaps | MWP/CAD plus ASI architecture artifacts | capability/status/authority separation | ASI map is not a live capability grant |
| **H10.10 Computational pipelines & reproducibility** | pipelines, shared configs, data, schemas, validators, CI, maintenance, drift detection | Git source, pipeline outputs, manifests and CI | reproducible source→result receipts | generated figure/output is not independently validated evidence |
| **H10.11** | Publication, DOI & public-artifact governance | `docs/public`, Figshare, DOI map, changelog, GitHub Pages, energyflow-cosmology.com, magnusson.as and the Morten-owned propagation pipeline | maintenance/CI/Figshare + pipeline receipts | publication/pipeline status is not scientific truth |

## Authority map

```text
ORCID                    → author identity
energyflow-cosmology.com → public programme narrative
GitHub EFC               → source/packages/pipelines
Figshare/DOI             → publication and evidence provenance
docs/public              → published artefact surface
Symbiose/graph           → typed projection only after writer/readback gate
MWP/CAD                  → architecture intent and governance
Opus/agent runtime       → operational execution only after runtime gates
```

## Required claim-status vocabulary

Every TheoryHomeRecord and graph projection must classify content as one of:

```text
DEFINITION
ONTOLOGY
HYPOTHESIS
MODEL_EQUATION
METHODOLOGY
PREDICTION_SEALED
PREDICTION_TESTED
EVIDENCE_INTERNAL
EVIDENCE_EXTERNAL
CONSISTENT_WITH
CONFRONTED_EXTERNAL
FALSIFIED_VARIANT
VALIDATION_PENDING
ARCHIVED
ARCHITECTURE_INTENT
RUNTIME_DECLARED
RUNTIME_LIVE_VERIFIED
```

`CONSISTENT_WITH` must never be silently promoted to `CONFIRMS`. `RUNTIME_DECLARED` must never be silently promoted to `RUNTIME_LIVE_VERIFIED`.

## Steward split inside one H10 domain

The primary `efc-asi-steward` may coordinate all lanes, but it must expose bounded sub-scopes:

```text
identity/provenance
programme/public
ontology/physical EFC
epistemology/EBE/regimes
measurement/RCMP
validation/prediction
consciousness/meta
Symbiosis/VAAI
ASI OS/map
pipelines/reproducibility
publication/DOI governance
```

Sub-stewards may propose and reconcile metadata. They do not inherit Morten's owner authority, graph-write authority, public-publish authority or ASI runtime authority.

## Public update rule

`docs/public/` and energyflow-cosmology.com are public surfaces, not scratchpads. A proposed change must carry:

```text
source package
source commit
DOI/evidence reference when applicable
claim status
validation/CI receipt
reviewer/owner decision
public commit/URL
MWP readback
```

Public publication remains `validate → review → publish → readback`; the H10 steward cannot bypass this sequence.

## Next reconciliation

Reclassify the 178 generated TheoryHomeRecords against H10.0–H10.11 using `index.json`, `schema.json`, DOI metadata, validation ledgers and public references. Retain `UNCLASSIFIED` where evidence is insufficient. Produce a second readback with lane, claim status, provenance, public impact and graph status per record.
