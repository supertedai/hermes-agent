# CASE-IDENTITY-01 — Remote broker closure plan

**MWP:** `MWP-UOSH-001`  
**Gap:** `GAP-IDENTITY-REMOTE-001`  
**Status:** `IMPLEMENTATION_PLAN / NOT_CLOSED`  
**Mode:** metadata-only; no credential, user-store, session-store or production mutation

## Owner decision — canonical login surface

Morten selected one canonical login surface:

```text
https://ai.byopus.com
```

It remains the browser and Desktop login surface and is protected by the
existing broker 2FA flow. Desktop must not implement a second password/TOTP
login and must not receive or persist the broker credentials. After the browser
session is authenticated, the broker must issue a short-lived, single-use
Desktop WebSocket handoff/ticket for the same authenticated principal.

This is the preferred architecture over separate browser and Desktop logins:

```text
ai.byopus.com 2FA login
  → broker opus_session
  → authenticated principal
  → single-use Desktop /api/auth/ws-ticket
  → Hermes /api/ws
  → session/device/transport binding
```

The handoff must be scoped, expiring, non-replayable and metadata-auditable;
it must not expose the password, TOTP secret, cookie or long-lived gateway key
to the Desktop renderer.

## Verified broker discovery

The existing canonical frontend/auth broker was reached read-only over the configured SSH authority `box14`:

```text
host: box14 / 192.168.40.14
process: /Users/hermes/symbiose-chat-prototype/hermes_ws_proxy.py
listener: *:9120
WebSocket route: /ws
auth route: /auth/login
identity read route: /api/me
```

The broker contract is server-authoritative:

```text
opus_session cookie
  → auth_mw
  → _subject_kind / _req_identity
  → canonical user authority
  → _stamp_prompt_identity
  → prompt.submit user_id
  → client + durable session identity binding
```

The broker removes or overwrites a client-provided `user_id`; it does not trust a renderer assertion.

## Required rehome

`ai.byopus.com` is the canonical **Cloud Endpoint**. It must not be started
directly as an Agent Endpoint from `.14`. The active Desktop surface must use
the Cloud Endpoint, whose Traffic Policy forwards internally to the separate
Agent Endpoint started by `.14`:

```text
Desktop → https://ai.byopus.com
        → Cloud Endpoint Traffic Policy: forward-internal
        → https://default.internal
        → .14 Agent Endpoint → localhost:9120
        → hermes_ws_proxy.py `/ws`
        → authenticated principal
        → Hermes gateway
```

Current read-only endpoint evidence:

```text
cloud endpoint: https://ai.byopus.com
cloud policy: forward-internal → https://default.internal
agent endpoint id: a8d498ac5df82670ff376fb7a90b8e24
agent endpoint target: .14 localhost:9120
cloud response: 302 /auth/login → broker login page
```

`default.internal` is an internal upstream name and must never be opened in
Firefox. A gateway health response alone is not sufficient evidence.

## Required metadata-only readback

Add or expose a broker-authenticated readback returning only:

```text
status
authenticated_user_id
conversation_id
client_session_id
durable_session_id
login_surface_id
device_id
device_class
transport
ssh_hop_ref
broker_session_ref
recorded_at
freshness
provenance
```

The route must derive `authenticated_user_id` from broker request context. It must not accept `user_id` from the request body as authority and must not return passwords, TOTP secrets, tokens or private content.

## Acceptance gates

1. Desktop connection is rehomed through broker `/ws`.
2. `/api/me` returns authenticated principal metadata for the active login.
3. `prompt.submit` receives broker-stamped identity, not renderer identity.
4. Both client and durable session IDs are bound and read back.
5. Device identity and SSH/gateway provenance are bound and read back.
6. Missing, expired, mismatched and revoked identity paths fail closed.
7. Same-session read-after-bind passes.
8. Restart/resume readback passes.
9. MWP receipt includes status, scope, freshness, provenance and rollback/revocation evidence.

## Current blocker

The active Desktop surface is now proven rehomed through the broker: `/api/status`
and `/api/auth/providers` return 200, `/api/auth/ws-ticket` returns 200 for the
authenticated session, and `/api/ws` upgrades with 101. The remaining blocker is
the positive metadata-only readback: a fresh authenticated `/api/mwp/identity`
receipt containing client/durable session IDs, device identity and transport
provenance has not yet been captured. Therefore `GAP-IDENTITY-REMOTE-001`
remains `PARTIAL / NOT_CLOSED`, not `CLOSED`.

## Non-goals

- no new auth provider
- no new user store
- no direct Desktop write to `users.json`
- no client-asserted principal
- no password/TOTP handling in MWP
- no graph, Qdrant, memory, scheduler or production mutation
