# MWP-UOSH-001 — Architectural risks / tail-biting audit

## RISK-01 — Two Hermes homes and runtime split

`~/.hermes-gui` and `~/.hermes` are both active surfaces. The canonical user store is pinned through `SYMBIOSE_USERS_HOME`, while skills/runtime state remain local to the asking process.

**Risk:** identity, capability inventory, skills, sessions and memory can appear healthy on one surface and be absent on another.

**Control:** keep canonical users/session authority explicit; build a service registry with home/profile/reader/writer; add cross-home readback tests.

## RISK-02 — Client session ID versus durable session ID

Existing `prompt.submit` binds both IDs, which fixes a real historical bug but leaves two identifiers that every new integration must carry correctly.

**Risk:** one path records identity/evidence under only one ID, producing silent `no_identity`, wrong scope or apparent legacy/admin fallback.

**Control:** define a typed session-lineage receipt and require both IDs at every boundary; test first turn, resume, restart, compression and queue drain.

## RISK-03 — Legacy owner fallback

The original single-user system uses a legacy owner/admin path, while identified multiuser sessions must fail closed.

**Risk:** a missing identity can be interpreted as legacy owner in one path and unknown user in another; Joakim could receive Morten's scope.

**Control:** classify explicitly: `legacy_owner`, `authenticated_multiuser`, `missing_identity`, `corrupt_identity`, `expired_identity`; never infer owner for an identified multiuser path.

## RISK-04 — File-based identity write concurrency

`session_identity.py` uses an in-process threading lock and atomic replace. Multiple processes/hosts can still race because the lock is not an interprocess lock shared by all writers.

**Risk:** concurrent writers can lose another process's new session binding or create stale readback.

**Control:** audit all writers; add a cross-process lock or move the write behind the existing authenticated authority; add concurrent write/readback and restart tests before broad automation.

## RISK-05 — Multiple task authorities

GUI Project, Hermes todo, Kanban, FaberGoalRegistry and evidence ledger all exist.

**Risk:** status drift, duplicate tasks and parent closeout disagreement.

**Control:** Kanban should be canonical task/case state; GUI Project is the human workspace/index; FaberGoalRegistry remains Faber-goal state; evidence ledger remains evidence. Add IDs/foreign references, not duplicated lifecycle state.

## RISK-06 — No authoritative BL/ADR registry

BL/ADR IDs occur in source/docs/tests and historical backups, but there is no single reconciled registry available in the audited workspace.

**Risk:** duplicate decisions, stale references and accidental new IDs.

**Control:** build a read-only registry/reconciliation matrix first; classify active/historical/stale/conflict/unmapped; owner-gate all new records.

## RISK-07 — `.12` versus `.13` runtime ownership

Both hosts expose unified_api-looking roots, while source references assign different roles to `.12` and `.13`.

**Risk:** writes/readbacks hit different instances; health checks pass against the wrong service.

**Control:** verify service identity, instance ID, writer role, graph/Qdrant destination and auth scope from authenticated endpoints; never use port health as authority proof.

## RISK-08 — Symbiose status provider is read-only

The 20-layer provider reports canonical status but `sync_turn()` is read-only/no-op by contract.

**Risk:** status can look integrated while no durable write/promotion path exists.

**Control:** separate `status_reader`, `canonical_writer`, `promotion_gate` and `read_after_write`; never promote status to write capability.

## RISK-09 — Auth-broker/client boundary

`/brukere` login-check is admin-gated; Desktop remote OAuth/token auth is a different concern.

**Risk:** a rushed bridge leaks admin credentials, accepts renderer-asserted user IDs or equates provider tokens with local user IDs.

**Control:** identify/reuse a trusted auth-broker/session handshake; Desktop receives only the authenticated result, never the store credentials.

## RISK-10 — Test execution depends on runtime context

The active gateway context cannot run the repository pytest baseline because of process/environment restrictions; isolated worktrees also lack the shared venv.

**Risk:** false confidence, delayed verification and unrepeatable closeout.

**Control:** establish a documented separate-runtime test runner before scheduler activation; record environment, profile, command and result in evidence.

## RISK-11 — Topology inventory from textual references

Repo/docs contain many historical, backup and binary/PDF references to BL/ADR/CAD/graph IDs.

**Risk:** false coverage and collision reports.

**Control:** source-priority classification and canonical registry; binary/history hits are leads only.

## RISK-12 — Unbounded MWP task register

The working task list is useful for planning but is not itself a durable execution authority.

**Risk:** task duplication, context drift and impossible parent closeout.

**Control:** keep the master list as index/readback; materialize executable cases in Kanban with stable `mwp_id/case_id/task_id`, dependency links and evidence references.
