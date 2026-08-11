# MWP-UOSH-001 / CASE-IDENTITY-01 — Desktop user binding

## Parent

- MWP: `MWP-UOSH-001`
- Autonomy contract: `docs/mwp-uosh-bounded-autonomy-contract.md`
- Workflow: `mwp-uosh-orchestration`
- Case status: `DISCOVERY`
- Blast radius: `R2` until proven narrower

## Objective

Bind the active Desktop session to the existing `/brukere` canonical user/capability authority and persist/read back `session_identity` without creating a parallel users store or guessing the owner.

## Existing authority

- User/capability UI: `http://localhost:9119/brukere`
- Canonical user store: `users.json` via `hermes_cli.dashboard_auth.user_store`
- Canonical path policy: `capability_policy.canonical_users_path()`
- Session binding: `hermes_cli.dashboard_auth.session_identity`

## Non-goals

- No new Desktop authentication provider.
- No new user store.
- No identity default to Morten/owner.
- No graph, Qdrant, memory or Obsidian write.
- No production restart or deployment.

## Discovery checklist

- [x] Desktop remote auth/connection path identified: OAuth/token gateway auth exists in `apps/desktop/src/components/first-run-remote-form.tsx` and `apps/desktop/electron/connection-config.ts`.
- [x] Desktop gateway boot/session path identified: `apps/desktop/src/app/gateway/hooks/use-gateway-boot.ts` and session stores.
- [ ] Desktop prompt/session creation path fully mapped.
- [ ] Backend prompt submission identity propagation identified.
- [x] `/brukere` canonical user/capability store identified: `hermes_cli.dashboard_auth.user_store` + `capability_policy.canonical_users_path()`.
- [x] `session_identity` read/write contract identified: `hermes_cli.dashboard_auth.session_identity`; atomic canonical file and server-side role lookup.
- [x] Missing active-session binding reproduced safely: active Desktop session is absent from canonical `session_identity.json`; environment user IDs are empty.
- [ ] Existing tests and negative paths mapped.
- [x] CAD-A/CAD-C/CAD-G relevance identified; runtime status remains open.
- [x] BL-2653/BL-2790/BL-3432 and ADR-046 references identified; owner/closeout reconciliation remains open.

### Current readback

```text
/brukere:  HTTP 200 (surface reachable)
/symbiose: HTTP 200 (surface reachable)
canonical session_identity mapping: NOT VERIFIED for the active Desktop session
```

The source contract confirms the canonical identity path is
`canonical_users_path().parent / session_identity.json`, with fail-closed reads.
Surface reachability is not evidence that the active Desktop session is bound to
`morten`; no owner identity is inferred from the HTTP 200 responses.


## Implementation checklist

- [ ] Smallest adapter/patch selected.
- [ ] Isolated worktree diff only.
- [ ] Fail-closed behavior preserved.
- [ ] Same-session read-after-write test.
- [ ] Restart/new-session readback test.
- [ ] Wrong-user/empty-identity negative test.
- [ ] Desktop/web/gateway identity parity test.
- [ ] Evidence attached to MWP task/case.
- [ ] Reviewer/owner gate evaluated.

## Closeout contract

Do not mark CLOSED without implementation, test, runtime readback, provenance, scope verification and rollback evidence.
