# MWP-UOSH — autonomous closeout protocol

## Authorization

Morten authorizes autonomous continuation of the MWP/ASI closeout sequence. The
agent may proceed through the task ledger without asking for a new confirmation
at every step.

## Autonomous operating rules

1. Continue the ordered MWP task/subgoal/goal ledger until the master coverage
   matrix is complete or an explicit blocker is recorded.
2. For every material change, drift event, flyby insertion, test result or
   promotion attempt, create a metadata-only change event with provisional
   `CAD-EVT-*`, `ADR-EVT-*`, and `BL-EVT-*` identifiers when canonical IDs are
   not yet allocated.
3. Scope every event by:

   ```text
   user_id + installation_id + login_surface_id + agent_id + system_scope
   ```

4. Log evidence references, status, freshness, owner, next action and gap.
5. Never claim a git, Neo4j or Obsidian update without a verifiable receipt from
   that destination.
6. Never promote `DECLARED`, `CACHED`, `UNKNOWN`, `STALE` or `UNVERIFIED` to
   `LIVE_VERIFIED` from static documentation alone.
7. Keep remote scans read-only unless a separately authorized adapter has an
   explicit write gate and returns a readback receipt.
8. Route non-trivial flybys to a bounded subagent, distill them, and insert only
   the metadata digest at a safe point without interrupting the primary loop.
9. If a subagent, adapter, test environment or authority is unavailable, record
   the missing evidence and continue with independent work.
10. Do not close the parent goal because only a partial child task is green.

## Closeout states

```text
COMPLETE       all required rows and destination receipts verified
OPEN           work remains but no hard safety blocker
BLOCKED        owner/gate/evidence prevents safe continuation
DRIFTED        runtime differs from CAD/ADR/BL/git/registry expectation
UNVERIFIED     source exists but live evidence is missing
```

The autonomous sequence is not permission to fabricate completion, bypass
consent, expose private payloads, or create a parallel authority.
