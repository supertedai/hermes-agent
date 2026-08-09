# MWP H10.11 — Morten-owned EFC publication pipeline contract

**Status:** `DECLARED / PIPELINE INTENT / RUNTIME GATED`  
**Owner:** Morten  
**Operator:** Opus + `efc-asi-steward` (proposed, not live-verified)  
**Scope:** EFC Git source, validation/CI, Figshare, `docs/public`, GitHub Pages, energyflow-cosmology.com, magnusson.as, DOI/manifests and MWP/graph projections

## 1. Architectural decision

Morten has one owned publication pipeline for the EFC/theory programme. Opus and the H10 steward shall be able to maintain and propagate validated changes across all connected publication surfaces instead of requiring independent manual edits in each surface.

```text
Morten-approved source change
        │
        ▼
EFC canonical Git repository
        │
        ├── package/index/schema/manifest sync
        ├── pipeline regeneration
        ├── validation ledger update
        ├── maintenance + drift detector
        ├── CI/test/reproducibility gates
        │
        ├── Git commit/push/readback
        ├── Figshare deposit/update + DOI metadata readback
        ├── docs/public generation/publish
        ├── GitHub Pages readback
        ├── energyflow-cosmology.com sync/readback
        ├── magnusson.as sync/readback where linked
        ├── MWP/CAD publication receipt
        └── Symbiose/graph typed projection after graph gate
```

The pipeline is **one orchestration contract**, not one undifferentiated authority. Each destination remains authoritative for its own result.

## 2. Surface authority

| Surface | Pipeline role | Destination authority |
|---|---|---|
| EFC Git repository | canonical source, code, package, schema and generated-source history | Git/source authority |
| EFC validation/maintenance | checks drift, package completeness, DOI and evidence rules | validation/CI authority |
| Figshare author/deposit profile | deposits, publication records, DOI metadata and files | Figshare/deposit authority |
| `docs/public/` | generated/public ledger/specification surface | public artifact source |
| GitHub Pages | public web rendering of repository artifacts | rendered public surface |
| `energyflow-cosmology.com` | public programme narrative/concepts/resources | website narrative surface |
| `magnusson.as` | Morten's authorial EFC surface | authorial programme surface |
| ORCID | persistent researcher identity | identity/provenance authority |
| MWP/CAD | architecture, owner, pipeline and receipt governance | governance intent/readback |
| Symbiose/graph | typed theory/publication projections | graph authority only after write/readback |

## 3. What Opus/H10 may automate

After a source change is accepted into the pipeline, Opus/H10 may automatically:

- detect affected packages, public pages, ledgers and manifests;
- run maintenance, drift and package validation;
- regenerate derived public artifacts;
- propagate DOI metadata and package references;
- prepare and execute Git updates through the approved writer;
- prepare and execute Figshare deposit/update through the approved publisher;
- synchronize linked website/public surfaces where their API/write route is configured;
- emit one publication/change receipt containing all destination statuses;
- update MWP/CAD metadata and typed graph projections after their gates pass;
- flag failures, drift or partial propagation without claiming completion.

## 4. Mandatory gates

Automatic propagation does not mean unreviewed scientific publication. The pipeline must distinguish:

```text
DRAFT
VALIDATION_RUNNING
VALIDATED
OWNER_APPROVAL_REQUIRED
PUBLISHING
PUBLISHED_PARTIAL
PUBLISHED
READBACK_VERIFIED
BLOCKED
ROLLBACK_REQUIRED
```

The following require Morten approval unless explicitly pre-authorized by a bounded policy:

- new or changed scientific claim;
- prediction status change;
- validation verdict change;
- kill-criterion result;
- change to equations, ontology or public interpretation;
- new Figshare DOI/deposit;
- public website narrative change;
- graph promotion from hypothesis/prediction/evidence to a stronger status;
- any external actuation or non-reversible publication action.

Routine mechanical propagation of an already-approved artifact may be automatic, but it still requires destination readback.

## 5. Publication receipt

Every pipeline run must emit a metadata-only receipt:

```text
pipeline_run_id
principal_id
owner_approval_ref
source_repo
source_commit
source_package_refs
validation_run_refs
claim_status
figshare_status
figshare_article_or_doi_ref
git_status
github_pages_status
energyflow_website_status
magnusson_website_status
mwp_status
graph_status
public_urls
freshness
provenance
rollback_ref
partial_failures
next_action
```

`PUBLISHED` is not allowed without destination evidence. `READBACK_VERIFIED` requires reading back every destination that the run claims to have updated.

## 6. Failure and rollback

The pipeline is fail-closed for claims and fail-visible for propagation:

- a failed Figshare write must not be reported as published;
- a Git update without public-page readback is `PUBLISHED_PARTIAL`;
- a public website update without corresponding source/commit provenance is `BLOCKED`;
- graph projection failure does not invalidate a successfully published artifact, but remains an open MWP receipt failure;
- partial propagation must retain exact destination statuses and next action;
- rollback uses source commit, Figshare version/deposit metadata and public artifact version references.

## 7. Current status

```yaml
owner: morten
pipeline_contract: DECLARED
opus_orchestration: PROPOSED
h10_steward_runtime: NOT_LIVE_VERIFIED
git_writer: EXISTING_SOURCE_SURFACE_BUT_PIPELINE_READBACK_REQUIRED
figshare_writer: DESTINATION_AUTHORITY_NOT_READBACK_VERIFIED
public_site_writers: ROUTES_NOT_READBACK_VERIFIED
mwp_receipt: DECLARED
parallel_public_update: NOT_ACTIVATED
graph_projection: BLOCKED
```

This contract authorizes the design of automatic propagation. It does not silently grant Opus credentials, Figshare publish authority, Git push authority, website write authority or graph-write authority.

## 8. First implementation/readback step

Build a metadata-only pipeline capability matrix with one row per destination:

```text
destination
writer/adapter
credential authority reference (never secret)
read route
write route
validation prerequisite
approval gate
rollback reference
freshness budget
current status
```

Then run a dry-run against one already-approved, non-claim-changing artifact before enabling automatic public propagation.
