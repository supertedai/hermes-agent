# MWP-UOSH — `.12` Life Contract/domain-agent daemon audit

**Audit mode:** read-only SSH inspection of `box12`  
**Target root:** `/home/byopus/AGI`  
**Finding:** POST-CREATION LIFE CONTRACT SYNC IS NOT CLOSED  
**Date:** 2026-08-06

## Relevant existing components

| Component | Observed responsibility | Direction |
|---|---|---|
| `tools/life_contract_aggregator_daemon.py` | Materializes canonical `:LifeContract` facts per `user_id/domain/predicate`; includes an `AGENTS` aggregator for already-existing FleetAgents | FleetAgent → LifeContract facts |
| `tools/life_contract_quality_guard.py` | Validates/archives invalid LifeContract facts; canonical user/domain checks | LifeContract validation |
| `apis/unified_api/steward_binding.py` | Resolves a classified domain by `(owner, domain)` to one steward, contract and cards; missing binding fails closed | read: `(user, domain)` → steward |
| `apis/unified_api/routers/life_contract_api.py` | `POST /life-contract/deploy-domain-agent` calls `agent_roster.register_agent`, sets steward properties, clears binding cache | domain-agent provisioning |
| `tools/agent_roster.py` | FleetAgent registration chokepoint | agent creation/update |
| `tools/steward_contract_emit.py` | Emits operational steward contract after steward exists and verifies graph/consumer | steward contract projection |
| `tools/user_provisioning_daemon.py` | Phase-0 user node/Qdrant/permissions/signal provisioning; explicitly a stub and provisioning is disabled by default | user provisioning only |
| `tools/domain_bridge.py` | Resolves observed feed/knowledge values to existing domain-steward FleetAgents; binds source ownership | external value/source → existing steward |

## Exact gap

The live `deploy_domain_agent` route currently performs:

```text
owner/trusted-source gate
→ normalize principal
→ owner-only check
→ derive steward slug
→ reject relabeling a non-steward FleetAgent
→ agent_roster.register_agent(... owner=principal)
→ SET FleetAgent.kind/domain/_archived/memory_scope/metadata
→ clear steward_binding cache
→ return deployed
```

It does **not** perform or verify:

```text
→ create/reconcile UserDomain for (user_id, domain_id)
→ create/reconcile the domain's agent binding key
→ write actual agent_id/domain_id back to the user's Life Contract
→ verify contract → domain → agent → contract round trip
→ return SYNCED only after the post-creation readback
```

The route response itself says the operational contract must be emitted later
with `tools/steward_contract_emit.py`, confirming that deployment and contract
sync are currently separate steps.

## Additional observed risks

1. The route is owner-only and uses the mutating principal, so it is not yet a
   complete per-user domain provisioning route.
2. The route writes `memory_scope="lifecontract:{domain}"`; this is not a
   user-scoped memory key and can collide when multiple users hold the same
   domain. The owner-keyed `steward_binding` reader expects `(owner, domain)`
   and documents the owner-scoped form.
3. `life_contract_aggregator_daemon.aggregate_agents()` runs in the opposite
   direction: it reads FleetAgents already owned by a user and materializes
   `AGENTS` facts. It cannot prove that a LifeContract-created domain caused
   the correct FleetAgent to exist.
4. `steward_binding.resolve_steward()` correctly refuses fallback to another
   user's steward, but this makes a missing post-creation binding visible as
   unresolved rather than repairing it.
5. `user_provisioning_daemon.py` is Phase-0/stub-mode with
   `DISABLE_PROVISIONING=1` by default; it creates a user/permissions signal,
   not the complete domain/steward lifecycle.
6. `domain_bridge.py` resolves source/knowledge values to existing domain
   stewards. It is not the user Life Contract domain provisioner.

## Required closed sequence

The safe sequence is:

```text
Life Contract intent (user_id, domain_id, contract_version)
  ↓
UserDomain provisioner creates/reconciles domain
  ↓
Domain provisioner calls the sanctioned agent roster gate
  ↓
FleetAgent receipt proves (user_id, domain_id, steward_role, agent_id)
  ↓
Steward operational contract is emitted/reconciled
  ↓
Life Contract is synced with the actual domain_id, agent_id,
  binding_key and contract version
  ↓
Round-trip readback proves all three records agree
  ↓
status = SYNCED
```

Any missing receipt, user/domain mismatch, owner mismatch, agent mismatch,
contract-version mismatch or unresolved binding must produce `BLOCKED` or
`CONFLICT`, never a green deployment result.

## MWP-UOSH disposition

```text
Life Contract facts/aggregator:             OBSERVED / existing
Per-owner steward read binding:             EXISTING / fail-closed
Domain-agent deployment:                    EXISTING / incomplete lifecycle
Post-creation Life Contract sync:           MISSING / OPEN GATE
User-scoped memory_scope:                   INCONSISTENT / OPEN GATE
Round-trip contract-domain-agent evidence:   MISSING / OPEN GATE
```

No remote writes, restarts, deploys or daemon changes were made during this
audit.
