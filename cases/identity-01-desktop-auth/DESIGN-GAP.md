# CASE-IDENTITY-01 — Design gap and preferred bridge

## Finding

Desktop has an existing OAuth/token connection flow, but `prompt.submit` currently sends only session/text/turn flags from the Desktop submit path. The backend already accepts a server-validated `user_id` and writes both client and durable session IDs into the canonical `session_identity` store.

The existing `/brukere` `login-check` route is admin-gated. Desktop must not receive or store `/brukere` admin credentials and must not write `users.json` directly.

## Preferred design

Reuse an existing authenticated auth-broker/session handshake:

```text
Desktop auth/connection
→ authenticated gateway/proxy session
→ server-side principal resolution from `/brukere`
→ session binding (`client_session_id` + `durable_session_id`)
→ prompt.submit/tool gates
```

The principal must be returned by a trusted server-side auth path, not asserted by the renderer and not derived from a gateway token locally.

## Required contract

- Desktop receives only an opaque authenticated session/capability result or server-read principal metadata.
- Backend resolves role/capabilities from canonical `users.json`.
- `prompt.submit` binds both client and durable IDs using the existing implementation.
- Missing/expired/mismatched principal fails closed for scoped tools.
- Logout/revocation invalidates future session use.
- No direct Desktop write to `users.json`.
- No password or TOTP secret stored in renderer state, project files or evidence.

## Alternatives rejected for now

1. Add `user_id` from renderer config: client-asserted and unsafe.
2. Treat OAuth/token subject as Hermes `user_id`: provider-specific and not proven to match `/brukere`.
3. Directly call `/brukere/login-check` from Desktop with credentials: leaks the admin-gated contract into a new client and bypasses the intended auth broker.
4. Default missing Desktop sessions to Morten/owner: violates bounded autonomy and fail-closed identity.

## Gate

`OWNER_GATE / ARCHITECTURE DECISION REQUIRED`

The next implementation must identify the existing authenticated proxy/broker endpoint or obtain an owner-approved ADR for the smallest new handshake. No auth code is changed in this case until that authority path is verified.
