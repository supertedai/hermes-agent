# MWP-UOSH — user → Life Contract → domain → steward-agent lifecycle

## Canonical chain

```text
:User (principal)
  └─ owns → LifeContract(user_id)
       └─ declares → UserDomain(user_id, domain_id)
            ├─ governed_by → DomainContract
            ├─ stewarded_by → FleetAgent(agent_id)
            ├─ scoped_to → Consent/visibility policy
            ├─ reads_from → connectors and memory surfaces
            └─ reports → metadata-only readback
```

The user-scoped Life Contract is the canonical source for which domains exist
for that user. The domain card, steward profile, connector projection and
Mission Control row are derived views. None of those views may create a second
user/domain authority.

## Provisioning invariant

Creating or activating a `(user_id, domain_id)` binding must be idempotent and
must reconcile the complete projection:

1. validate the principal and user Life Contract;
2. resolve the canonical domain definition and named steward;
3. create or reconcile exactly one user-domain binding;
4. create or reconcile the steward-agent binding for that user/domain;
5. apply consent, visibility, memory scope and connector references;
6. emit a metadata-only sync/readback record;
7. leave unresolved capabilities or missing runtime evidence explicitly gated.

A repeated reconcile must not create a second agent, duplicate a contract, or
silently broaden scope.

## Agent identity rule

A global steward name such as `daedalus` or `faber` identifies the role/type.
The per-user materialized binding must additionally carry a stable user/domain
key, for example:

```text
agent_binding_key = <user_id>:<domain_id>:<steward_role>
```

The role name alone is never sufficient ownership evidence. A global fleet
agent and a user-domain steward projection are separate runtime levels and
must not be conflated.

## Sync directions

### Life Contract → projections (authoritative)

- domain created, renamed, disabled or archived;
- steward role changed;
- sharing/privacy/consent changed;
- connector set changed;
- memory scope changed;
- user disabled or reactivated.

Each event reconciles the user-domain binding and emits a versioned readback.

### Runtime/domain agent → Life Contract (bounded feedback)

Agents may report metadata such as:

- beat/health;
- capability and skill measurements;
- connector health;
- open gates;
- observed gaps;
- proposal references;
- measured outcomes.

Agents may not silently create a new user domain, widen consent, grant a
capability, or change the canonical Life Contract. Those require the existing
user/admin/governance gate.

## Required identity/scope tuple

Every projection and readback must retain:

```text
principal_id
life_contract_id
user_domain_id
domain_id
steward_role
agent_binding_key
profile
consent_version
memory_scope
connector_refs
source_version
runtime_version
readback_status
rollback_ref
```

## Readback statuses

```text
DISCOVERED
CONTRACT_VERIFIED
DOMAIN_BOUND
AGENT_BOUND
SYNCED
STALE
CONFLICT
BLOCKED_IDENTITY
BLOCKED_CONSENT
BLOCKED_RUNTIME
ROLLBACK_REQUIRED
```

`SYNCED` requires both a canonical contract version and a matching projection
readback. A UI card that merely renders is not `SYNCED`.

## Safety and authority gates

- The canonical user registry is the source of valid principals; daemon-local
  literal user lists are fail-safe floors only, never a competing truth.
- User deletion/disable must not silently delete historical ownership or
  auto-archive user-owned facts. Access and ownership retention are separate.
- Health, identity and financial domains retain their stricter gates.
- The Helse/health steward must never turn a shared UI readback into raw clinical
  context.
- Connector credentials remain in the credential/Vault authority; the Life
  Contract stores references and status, not secrets.
- A missing steward/runtime binding is visible as `BLOCKED_RUNTIME`, not as an
  empty domain or a newly invented fallback agent.

## MWP-UOSH mapping

The master coverage matrix must add lifecycle rows for:

- user registry → Life Contract resolution;
- Life Contract → per-user domain materialization;
- domain → named steward resolution;
- user/domain → agent binding reconciliation;
- consent/privacy → memory and connector scope;
- agent/runtime → metadata-only feedback;
- disable/archive → ownership retention and rollback;
- Mission Control → lifecycle readback only.

This is a governance/projection contract. It does not authorize a new writer,
provisioner, scheduler or Desktop route by itself.
