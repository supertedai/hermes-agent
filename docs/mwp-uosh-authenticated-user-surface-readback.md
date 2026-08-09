# MWP-UOSH — authenticated user-surface readback

**Source class:** user-provided authenticated UI readback  
**Principal:** `morten`  
**Role shown:** `Admin`  
**Status:** SURFACE_OBSERVED / AUTHORITY_AND_LIVE_API_PENDING  
**Scope:** Opus/Symbiose user portal and Life OS surfaces

## Domain inventory

The user readback shows 14 domain surfaces:

| Domain | Steward | Sharing/brain marker | Surface status |
|---|---|---|---|
| AGENTS | Argos | inherited | observed |
| Helse | Asklepios | inherited | observed |
| SKILLS | Athena | inherited | observed |
| Prosjekter | Daedalus | own brain | observed |
| Kode | Faber | full stack | observed |
| Eiendom | Gaia | inherited | observed |
| Energi | Helios | full stack | observed |
| Arbeid | Hephaistos | inherited | observed |
| Familie | Hestia | inherited | observed |
| Grensesnitt | Iris | inherited | observed |
| Identitet | Janus | inherited | observed |
| Økonomi | Plutus | inherited | observed |
| Sted | Terminus | inherited | observed |
| THEORIES | Urania | inherited | observed |

The readback reports `2/14` domains with full cognitive stack, `8` abilities
per agent, and `2` gates awaiting the principal. These values are UI-reported
metadata and remain unpromoted until the underlying readback route is verified.

## Principal/admin surfaces observed

- Profile
- Security and login
- Account
- Life / domains
- Consent and privacy
- Memory and provenance
- Opus customization
- Notifications
- Users
- Groups and access
- Governance
- API and keys
- Documents / project ingest
- Sources / connectors
- Conversations
- Opus identity and runtime explanation

## Agent/domain surface metadata

The readback exposes domain cards with:

- named steward
- domain responsibility
- inherited/own/full cognitive-stack marker
- skills count and sharing classification
- domain detail route
- connectors and consent
- goals and runtime beat metadata
- cognitive capabilities and gates
- memory-layer measurements
- track record and measured outcomes
- gaps, proposals and enactment gates

## User-level Opus readback metadata

The readback shows user-scoped metadata including:

- principal `morten`
- admin role
- user-vs-agent memory distinction
- separate `own` and `reachable-via-stewards` memory counts
- per-user recall gating
- provenance/source ownership
- conversation embedding and learning-wire counters
- invariant count
- per-user clinical-content exclusion rule
- domain sharing and consent semantics

Raw conversation text, memory bodies, source payloads, credentials and private
content are intentionally not copied into this artifact.

## MWP classification

| Surface class | What is proven | Current classification |
|---|---|---|
| Authenticated user portal | The user supplied a readback from an authenticated admin surface | `USER_PROVIDED_READBACK` |
| Domain/steward catalog | 14 named domains and steward identities are visible | `SURFACE_OBSERVED` |
| Admin controls | Users, groups/access, governance and API/key sections are visible | `SURFACE_OBSERVED` |
| Connectors/consent | Domain cards expose connector and consent concepts | `SURFACE_OBSERVED` |
| Live backend authority | Not established by the pasted UI readback alone | `AUTHORITY_PENDING` |
| Route-level readback | Not established for every child route | `ROUTE_PENDING` |
| Runtime/Cortex state | UI metadata is visible; live runtime ownership still needs direct evidence | `RUNTIME_PENDING` |
| MWP matrix closure | This expands the matrix but does not close it | `INCOMPLETE` |

## Next verification gates

1. Obtain route/API evidence for the authenticated user portal without exposing
   credentials.
2. Map each domain card to its canonical surface ID and authority owner.
3. Verify user/admin/group/governance/API routes and their readbacks.
4. Separate UI-reported cognitive/memory counts from live graph/runtime evidence.
5. Add the verified rows to the master coverage matrix and let the continuation
   loop reevaluate completion.
