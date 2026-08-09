# MWP/CAD — tenant-, domene- og visningsflatearkitektur

**Status:** `DECLARED` / architecture intent  
**Owner:** Morten  
**Scope:** MWP-UOSH, Opus control plane, Life Contracts, Opus-interne systemdomener og Morten-eide virksomheter  
**Mutation policy:** Dette dokumentet er CAD/MWP-intent. Det gir ikke i seg selv runtime-authority, agent-authority eller produksjonsaktivering.

## 1. Arkitekturvedtak

Opus skal være én samlet **control plane og intelligence layer**, men ikke én sammenblandet datamasse eller én flat operativ visningsflate.

```text
Canonical login
└── Opus control plane
    ├── Identity & Authority
    │   └── Morten — øverste admin/authority-holder
    ├── Personal tenant
    │   └── Morten sine LifeContract-domener og steward-agenter
    ├── Opus system tenant
    │   └── interne systemdomener, blant annet Security/Cyber/Sentinel
    ├── Company tenants
    │   └── én isolert tenant per juridisk/operativ virksomhet
    └── Portfolio projections
        └── autoriserte, metadata-/KPI-baserte tverrtenant-visninger
```

**Kjerneinvariant:** Én loginflate og én overordnet styringsmodell betyr ikke at alle tenants, rådata eller operative UI-flater skal blandes.

## 2. Tenants og domener

### 2.1 Personal tenant — Mortens liv

Life Contracts er den autoritative kilden for Mortens livsdomener. Hvert domene materialiseres med egen user-domain-binding og egen steward-binding:

```text
Morten / Personal
├── Helse       → Asklepios
├── Prosjekter  → Daedalus
├── Eiendom     → Gaia
├── Energi      → Helios
├── Arbeid      → Hephaistos
├── Familie     → Hestia
├── Identitet   → Janus
├── Økonomi     → Plutus
└── Sted        → Terminus
```

Et livsdomene er ikke det samme som en bedrift, en Opus-intern tjeneste eller en tilfeldig dashboardfane. LifeContract → UserDomain → DomainContract → FleetAgent er den kanoniske kjeden.

### 2.2 Opus system tenant — Opus sitt interne system

Opus-interne systemdomener skal ikke modelleres som Mortens private livsdomener, selv om Morten har øverste admin-/authority-rolle:

```text
Opus / System
├── Security
│   └── Cyber → Sentinel / symbiose-cyber
├── Memory
├── Learning
├── Agent Fleet
├── Infrastructure
├── Governance
└── Runtime / Observability
```

Cyber er derfor et Opus-systemdomene under Security, med eksisterende live Cyber-agent/steward `Sentinel`, ikke et nytt personlig LifeContract-domene.

### 2.3 Company tenants — virksomheter

Hver juridisk eller operativ virksomhet får en separat tenant med:

- egen identitet og rollemodell;
- egne agenter og domain stewards;
- egne connectorer og credentials-referanser;
- egne workflows, audit- og compliance-regler;
- egen operativ cockpit;
- eksplisitt policy for hvilke porteføljeprojections som kan vises til Morten.

En virksomhet kan være eid eller administrert av Morten uten å bli innlemmet i hans private livsflate eller få fri tilgang til Opus-systemdata.

## 3. Authority- og eierskille

| Principal/rolle | Authority-scope |
|---|---|
| Morten som livseier | Eier og styrer egne LifeContracts og personlige livsdomener |
| Morten som Opus-admin | Øverste admin-/authority-rolle over Opus control plane og Opus-systemdomener |
| Morten som selskapseier/admin | Authority innen de virksomhetstenants hvor han faktisk har slik rolle |
| Opus | Plattform, kontrollplan, policy- og intelligenslag; er ikke eier av Mortens liv eller bedriftenes juridiske data |
| Domain steward | Forvalter et avgrenset domene; eier ikke domenet |
| Operator-agent | Kan utføre bare eksplisitt tildelte operasjoner innen tenant/scope |
| LLM | Resonneringskomponent gjennom scoped tools; aldri system-of-record eller authority-holder |

**Invariant:** Registry-tilstedeværelse, deklarert capability og live runtime/authority må readback-verifiseres separat.

## 4. Visningsflater

### 4.1 Canonical login

Én canonical loginflate kan tilby context switching, men aktiv kontekst skal alltid være synlig:

```text
Aktiv kontekst: Morten / Personal / Energi
Aktiv kontekst: Opus / System / Cyber
Aktiv kontekst: Company-A / Operations
```

### 4.2 Personal cockpit

Viser Mortens livsdomener, LifeContracts, personlige mål og godkjente portefølje-sammendrag. Den viser ikke automatisk bedriftenes rådata, ansatte, kundedata, interne logger eller operative arbeidsflate.

### 4.3 Opus system cockpit

Viser Cyber/Sentinel, agentflåte, runtime, memory/learning, security, liveness, governance og systemdrift. Morten får admin-/oversiktsadgang, men systemdata skal fortsatt være semantisk skilt fra Personal.

### 4.4 Company cockpit

Hver virksomhet får egen operativ flate for virksomhetens data, brukere, workflows, agenter, KPI-er og tiltak. Denne flaten skal ikke bare være en ny fane i Personal.

### 4.5 Portfolio cockpit

Morten får en separat porteføljevisning med autoriserte projections:

- aggregert status og KPI;
- risiko og kritiske avvik;
- økonomisk sammendrag;
- åpne eierbeslutninger;
- agent-/systemhelse;
- lenke til riktig tenant.

Portfolio er en projection, ikke en global rådatamemory.

## 5. Bedriftsintegrasjon

Anbefalt modell er **Opus-integrert, API-avgrenset**:

```text
Opus control plane
└── tenant-aware policy/adapter layer
    └── Company tenant API gateway
        ├── ERP
        ├── CRM
        ├── økonomi/bank
        ├── HR
        ├── prosjektverktøy
        └── dokumenter
```

LLM skal ikke få direkte fri databaseadgang. En arbeidsflyt skal gå gjennom:

1. identity- og tenant-scope;
2. policy- og tool-allowlist;
3. minste nødvendige API-lesing;
4. LLM-resonnering;
5. forslag eller gated handling;
6. audit/provenance/readback;
7. rollback eller menneskelig godkjenning ved høy konsekvens.

Bedrifter med egne sensitive data, juridiske krav eller høy operasjonell risiko bør ha egne tenant-agenter/runtime. Opus kan orkestrere og levere intelligence, men skal ikke viske ut tenant-grensene.

## 6. Data- og proveniensregler

Som standard kan bare eksplisitte projections krysse tenant-grenser:

- status, KPI, risiko og agenthelse;
- eierbeslutninger og kritiske hendelser;
- godkjente økonomiske sammendrag;
- lenker til kilde-tenanten.

Rå helseopplysninger, personopplysninger, kundedata, ansattdata, credentials, full dokumentarkiv og detaljerte sikkerhetslogger skal ikke kopieres til global Opus- eller Personal-memory uten eksplisitt consent/policy.

Hver projection må bære minst:

```text
source_tenant
source_record_or_metric
principal_id
consumer_scope
consent_version
provenance
freshness
runtime_version
readback_status
rollback_ref
```

## 7. Anti-patterns

Følgende er eksplisitt forbudt som arkitekturretning:

1. Alt trekkes inn i Morten-fanen.
2. Bedrifter modelleres som Mortens LifeContracts.
3. Agenten behandles som eier fordi den har steward-rolle.
4. Registry eller CAD behandles som live authority uten readback.
5. Full virksomhetsdatabase kopieres til LLM eller global memory.
6. Én global memory store brukes på tvers av Personal, Opus System og Company tenants.
7. Bedriftsoperasjoner utføres uten tenant-aware API, audit og approval-gate.
8. Cyber/Sentinel blandes semantisk inn i Personal bare fordi Morten er admin.

## 8. MWP/CAD-gater

Dette dokumentet kan promotere arkitekturintensjonen, men følgende må verifiseres før `SYNCED` eller `LIVE_VERIFIED`:

- LifeContract → user-domain → steward-agent roundtrip for Personal;
- tenant registry og juridisk/operativ owner-readback for hver bedrift;
- canonical identity/authority-readback for Morten per tenant;
- company API gateway med scoped tools og audit;
- portfolio projection med provenance/freshness/rollback;
- GUI context switch/readback per user og tenant;
- live Cyber/Sentinel authority og scope under Opus System/Security;
- graph write/read-after-write og eventuell canonical Obsidian receipt.

## 9. Status og neste steg

```yaml
intent: DECLARED
personal_life_domains: ARCHITECTURE_DEFINED
opus_system_domains: ARCHITECTURE_DEFINED
company_tenants: ARCHITECTURE_DEFINED
portfolio_projection: ARCHITECTURE_DEFINED
runtime_authority: BLOCKED_UNTIL_READBACK
canonical_graph_write: BLOCKED
canonical_obsidian_write: BLOCKED
production_activation: NOT_AUTHORIZED
owner: morten
```

Dette dokumentet er den arkitektoniske plasseringen av beslutningen i MWP/CAD. Det etablerer ikke i seg selv en ny agent, en ny tenant eller en ny runtime-writer.
