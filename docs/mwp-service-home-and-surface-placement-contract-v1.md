# MWP-UOSH — service-home og surface-placement contract

**Status:** `DECLARED / PLACEMENT GATE OPEN`  
**Owner:** Morten / MWP control-plane authority  
**Scope:** alle Symbiose-/Opus-flater, tjenester, agenter, daemons, tiles, tabs, user-/company-tenants og projections  
**Evidence baseline:** live Symbiose census `676 surfaces / 61 tabs / 173 tiles / 442 services / 100% owned`, men uten komplett per-service home-readback

## 1. Problem og vedtak

At en tjeneste finnes i Symbiose-censuset eller vises under en tab er ikke nok til å si hvor den hører hjemme. Faner er visningsprojeksjoner; MWP trenger et eksplisitt **service home** som binder hver tjeneste til riktig owner, tenant, domain, steward, authority, surface og runtime.

**Vedtak:** Ingen service, daemon, agent, tile eller connector er arkitekturelt komplett før den har et deterministisk MWP-home. `OVERSIKT` og `01–05` er navigasjons-/projection-grupper, ikke eierskap eller authority i seg selv.

## 2. Kanonisk service-home

```text
ServiceRecord
  ├── service_id / stable_identity
  ├── service_kind
  ├── owner_principal
  ├── tenant_id
  ├── domain_id (nullable only for shared/platform services)
  ├── steward_agent_id (nullable only for human/platform-gated services)
  ├── authority_scope
  ├── data_scope / consent_scope
  ├── canonical_surface_id
  ├── navigation_group (OVERSIKT or 01–05)
  ├── runtime_host / process / container
  ├── source_authority
  ├── freshness / provenance
  ├── readback_status
  └── rollback_ref
```

Et service-home er gyldig først når `tenant_id`, `owner_principal`, `authority_scope`, `canonical_surface_id` og `readback_status` er til stede. `domain_id` og `steward_agent_id` kan være `null` for shared control-plane/infrastructure, men da må `service_kind` og human/platform owner forklare hvorfor.

## 3. Home-klassene

### H0 — Personal / user-admin

**Tenant:** `personal:{user_id}`  
**Owner:** Morten eller annen eksplisitt bruker  
**Surface:** Personal cockpit / brukerens adminflate  
**Eksempler:** brukerpreferanser, personlige mål, private consent-/identity-tjenester.

Disse er Mortens eller brukerens domene. De skal ikke automatisk bli Opus-systemdata eller company-data.

### H1 — Personal LifeContract domain

**Tenant:** `personal:{user_id}`  
**Domain:** Helse, Prosjekter, Eiendom, Energi, Arbeid, Familie, Identitet, Økonomi eller Sted  
**Steward:** Asklepios, Daedalus, Gaia, Helios, Hephaistos, Hestia, Janus, Plutus eller Terminus  
**Surface:** Personal domain cockpit + godkjent Portfolio projection.

Kanonisk kjede:

```text
User → LifeContract → UserDomain → DomainContract → steward-agent → service projection
```

### H2 — Opus internal system

**Tenant:** `opus:system`  
**Owner:** Morten som Opus-admin; systemansvarlig agent/role etter domain  
**Surface:** Opus System cockpit  
**Eksempler:** Memory, Learning, Runtime, Governance, Infrastructure og Security.

### H3 — Opus internal security/domain

**Tenant:** `opus:system`  
**Domain:** `security/cyber`  
**Steward:** `Sentinel / symbiose-cyber`  
**Surface:** `05 · VERDEN & DOMENER → Cyber` samt Opus System/Security cockpit.

Cyber er et Opus-systemdomene, ikke et nytt Personal LifeContract. NVD, EDR, Suricata/Snort, PA-440, DNS/sinkhole, exfil-/beaconanalyse, AI-injection-gate og cyber-fusjon skal få home under denne klassen med egne service-records.

### H4 — Agent/fleet control

**Tenant:** `opus:system` eller eksplisitt fleet-tenant  
**Owner:** Morten/Opus control plane  
**Steward:** Argos eller annen verifisert fleet-steward  
**Surface:** `OVERSIKT → Eierskap/Fleet Worker`, `02 → Agenter/Agent-aktivitet`.

Registry, capability, liveness, runtime namespace, role/provider og handoff er separate service-records. Fleet membership alene gir ikke service-authority.

### H5 — Shared MWP control-plane

**Tenant:** `mwp:control-plane`  
**Owner:** Morten / MWP authority  
**Surface:** `OVERSIKT → Kart/Executive/Orkestrering` og relevante `01–04` governance-/driftflater.

Eksempler: topology, change ledger, receipt coordinator, gap register, identity propagation, cross-surface truth og gate evaluators. Disse skal ikke feilplasseres som et livsdomene bare fordi de vises i Morten-admin.

### H6 — Company tenant

**Tenant:** `company:{legal_entity_id}`  
**Owner:** juridisk/operativ virksomhet etter authority registry  
**Steward:** company-domain agenter  
**Surface:** separat Company cockpit; Portfolio viser bare autoriserte projections.

ERP, CRM, HR, prosjekt, økonomi, kundedata og interne company-daemons skal aldri plasseres direkte i Personal eller `opus:system` uten eksplisitt cross-tenant policy.

### H7 — Runtime/infrastructure

**Tenant:** installation/host-scoped  
**Owner:** infrastructure authority  
**Surface:** `04 · DRIFT & OVERVÅKNING`, `OVERSIKT → Surveillance/Ressurser`  
**Eksempler:** Docker/systemd/process/listener, host probes, gateway, network plumbing.

Runtime/home er ikke det samme som business/domain-home. En daemon som kjører på `.12` tilhører ikke automatisk `Helse`, `Cyber` eller Morten.

### H8 — Projection/read model

**Tenant:** consumer-scoped  
**Owner:** source domain beholder ownership  
**Surface:** Portfolio, Executive, Kart eller en domenefane.

En projection er ikke en ny eier, tenant eller memory authority. Den må peke tilbake til `source_tenant`, `source_service_id`, provenance, freshness og rollback.

### H9 — External gate / legacy / retired

Eksterne tjenester og historiske/retired daemons må få eksplisitt status. `legacy_daemon` er ikke det samme som live, og en ekstern provider er ikke Opus-eid bare fordi den vises i GUI.

## 4. Mapping til de fem gruppene

| Gruppe | Hva den er | Hva den ikke er |
|---|---|---|
| `OVERSIKT` | organism-/control-plane projections | canonical service ownership |
| `01 · STYRING & SELV` | autonomy, goals, Opus self/governance | all admin services indiscriminately |
| `02 · KOGNISJON & LÆRING` | cognition, memory, learning, agents and consequences | Personal LifeContract ownership by default |
| `03 · SANNHET & INTEGRITET` | source-of-truth, governance, ingest, maturity | graph write authority by display alone |
| `04 · DRIFT & OVERVÅKNING` | strategy, BL, runtime/operations views | tenant ownership |
| `05 · VERDEN & DOMENER` | external/world domains and approved domain cockpits | all internal services or all companies |

En tjeneste kan ha flere **read projections**, men bare ett kanonisk home. Eksempel: Cyber kan vises i `05`, `OVERSIKT` og Security cockpit, men eies ett sted: `opus:system/security/cyber`.

## 5. Morten og authority

```text
Morten
├── Personal authority over own LifeContracts
├── Opus-admin authority over opus:system
├── Company authority only where company registry grants it
└── Portfolio read/projection authority by explicit consent/policy
```

Agenten er steward/operator innenfor et home; den blir ikke eier. Registry, declared capability, live runtime og authority må readback-verifiseres separat.

## 6. Minimum promotion gate

Et service-home kan bare promoteres til `MAPPED_LIVE` når readback inkluderer:

```text
service_id
service_kind
owner_principal
tenant_id
(domain_id when applicable)
steward_agent_id / human-gate reason
authority_scope
canonical_surface_id
navigation_group
runtime_ref
source_authority
provenance
freshness
readback_status
rollback_ref
```

Status vocabulary:

```text
DISCOVERED
CLASSIFIED
DECLARED_HOME
MAPPED_LIVE
BLOCKED_OWNER
BLOCKED_TENANT
BLOCKED_STEWARD
BLOCKED_RUNTIME
BLOCKED_AUTHORITY
STALE
CONFLICT
RETIRED
```

`owned=676` eller `coverage_pct=100` er ikke tilstrekkelig for `MAPPED_LIVE`; census ownership og home placement er separate gates.

## 7. Første klassifiseringspass

Dette er arkitekturens startpunkt, ikke et påstått ferdig service-readback:

| Surface/familie | MWP-home | Status |
|---|---|---|
| LifeContract domain services | H1 Personal domain | `DECLARED_HOME` / roundtrip open |
| Cyber/Sentinel stack | H3 Opus Security/Cyber | `DECLARED_HOME`; live Cyber surface observed |
| Agent registry/capability/liveness | H4 Agent/Fleet control | `DECLARED_HOME`; runtime mapping partial |
| MWP gap/ledger/topology/receipt services | H5 Shared MWP control-plane | `DECLARED_HOME`; graph/Obsidian receipts blocked |
| Docker/systemd/process/listener probes | H7 Runtime/infrastructure | `DECLARED_HOME`; owner mapping required |
| Company ERP/CRM/HR/project services | H6 Company tenant | `BLOCKED_TENANT` until legal/entity registry exists |
| Executive/Kart/Portfolio/tiles | H8 Projection/read model | `DECLARED_HOME`; source/backlink readback required |
| External/legacy/retired daemons | H9 External/legacy/retired | `CLASSIFIED` only until lifecycle evidence |

## 8. MWP next action

Build a metadata-only `ServiceHomeRecord` projection over the live 442-service census. Do not create agents or write graph records from the census alone. For every row, return:

```text
service_id, home_class, owner, tenant, domain, steward,
canonical_surface, navigation_group, authority, runtime,
provenance, freshness, status, blocker, next_action, rollback_ref
```

The first completion target is not `100% green`. It is **100% classified with honest blockers**, followed by owner/tenant/steward/runtime reconciliation one home class at a time.
