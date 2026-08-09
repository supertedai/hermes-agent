# Hermes Desktop control inventory — MWP-UOSH-001

**Status:** PARTIAL / ACTIVE RECONCILIATION
**Scope:** `apps/desktop/src`
**Rule:** A renderer control is complete only when its authoritative owner, route, scope, readback and rollback are known.

## Verified connected controls

| Control group | Renderer | Authority/route | Readback/rollback | Status |
|---|---|---|---|---|
| Settings config autosave | `app/settings/config-settings.tsx` | `PUT /api/config` | `GET /api/config` before cache publication; stale-save generation guard | CONNECTED |
| Active session model picker | `app/session/hooks/use-model-controls.ts` | gateway `config.set` with explicit `session_id` and provider | backend `deferred`/session events; rollback on failure | CONNECTED |
| Reasoning/fast model controls | `app/shell/model-edit-submenu.tsx`, `store/model-presets.ts` | gateway `config.set` with session scope | rollback on failure; preset is local preference by design | CONNECTED |
| Approval mode | `store/approval-mode.ts` | `config.set` / `config.get` | authoritative returned value; rollback to confirmed mode | CONNECTED |
| Session/global YOLO | `lib/yolo-session.ts` | session/global `config.set` | returned `value`; backend scope is explicit | CONNECTED |
| Kanban orchestration | `plugins/kanban/orchestration.tsx` | plugin API mutation | React Query invalidation of orchestration/profiles | CONNECTED |
| Kanban task actions | `plugins/kanban/board.tsx`, `drawer.tsx` | Kanban plugin API / existing task authority | mutation/query invalidation path | CONNECTED, route audit retained |
| Memory provider OAuth | `app/settings/memory/connect.tsx` | provider OAuth API | polling status until terminal state; timeout/error path | CONNECTED |
| Memory provider config modal | `app/settings/memory/provider-config-modal.tsx` | `PUT /api/memory/providers/<provider>/config` | parent refresh after save | CONNECTED |
| Memory provider inline config | `app/settings/memory/provider-config-panel.tsx` | same provider config route | field-level `GET` readback; sibling drafts preserved | CONNECTED |
| Custom endpoints create/update | `app/settings/custom-endpoints-settings.tsx` | `saveCustomEndpoint` | response endpoint list rehydrates form/list | CONNECTED |
| Custom endpoint validate | same | `validateCustomEndpoint` | returned reachable/models used in form | CONNECTED |
| Custom endpoint activate/delete | same | `activateCustomEndpoint` / `deleteCustomEndpoint` | response/refresh endpoint list; active model callback | CONNECTED |
| Profile create/rename | `app/profiles/create-profile-dialog.tsx`, `rename-profile-dialog.tsx` | `createProfile` / `renameProfile` | parent refresh/select callback; failure keeps dialog open | CONNECTED |
| Cron create/update/delete/pause/resume/run | `app/cron/index.tsx` | existing Hermes cron API | query/store refresh and run-state readback | CONNECTED |
| Webhook enable/create/delete/toggle | `app/webhooks/index.tsx` | existing webhook API | React Query invalidation; restart-needed/error state | CONNECTED |
| Desktop plugin enable/disable/rescan | `contrib/plugins-store.ts`, `settings/plugins-settings.tsx` | Electron/Desktop plugin loader + localStorage decision store | loader handle/status; local authority by design, not backend config | LOCAL_BY_DESIGN |
| Main model/profile default | `app/settings/model-settings.tsx` | `setModelAssignment` / profile `PUT /api/config` | assignment response + config GET readback; profile/generation guard | CONNECTED |
| Agent reasoning/service-tier defaults | same | `PUT /api/config` | authoritative config GET; stale generation guard; rollback | CONNECTED |
| Auxiliary model assignments | same | `setModelAssignment(scope=auxiliary)` | auxiliary refresh/readback; stale-slot warning | CONNECTED |
| MOA preset/reference/aggregator settings | same | `saveMoaModels` | saved response + generation guard; incomplete slots held | CONNECTED |
| Fallback model settings | `app/settings/config-settings.tsx` | profile config PUT | authoritative config GET readback | CONNECTED |
| Gateway local/remote/cloud/SSH connection | `settings/gateway-settings.tsx`, `electron/connection-config.ts`, `app/gateway/hooks/use-gateway-boot.ts` | Electron connection authority + real WS/auth path | saved config readback; fresh OAuth ticket; real WS connect; reconnect/reauth/error ladder | CONNECTED |
| Active memory-provider selection | `app/settings/config-settings.tsx` / memory settings | profile config `memory.provider` | authoritative config GET readback; provider config/OAuth status separate | CONNECTED |
| Billing/account/usage read | `app/settings/billing/index.tsx` | billing API/provider | query state and refresh | CONNECTED |
| Credits/payment/auto-reload | `app/settings/billing/*` | external billing/payment provider | charge poller, settlement state, ambiguous/portal/retry/step-up paths | EXTERNAL_GATE |
| Command Center maintenance actions | `app/command-center/index.tsx`, `maintenance.tsx` | Hermes action API | action polling/log readback; curator/memory status refresh | CONNECTED |
| Session goals | `store/goals.ts` | session gateway `slash.exec goal status` + gateway goal events | session-scoped goal status readback; no execution authority in renderer | CONNECTED_READ_ONLY |
| Review/ship pane | `store/review.ts`, Electron git bridge | Electron/local git authority | git diff/status/readback; commit/push remains explicit gated action | CONNECTED_GATED |
| Faber/Opus automation execution | no direct Desktop route/control found | existing backend candidates: `FaberRuntime`/`FaberGoalRegistry` and loopback-only `/api/internal/tui/emit` with dedicated relay credential | Desktop must not call internal relay directly; requires typed authenticated principal/capability route, reviewer gate, evidence/readback | BLOCKED_UNWIRED |

## Local-by-design controls

These are not backend settings and must not be presented as global Hermes truth:

- model visibility and provider collapse (`store/model-visibility.ts`, `store/provider-collapse.ts`)
- per-model Desktop presets (`store/model-presets.ts`) until applied to a session
- layout, pane, zoom, statusbar visibility and window presentation
- search/filter/collapse controls
- local onboarding dismissal and local UI preferences

They still require explicit scope and must not leak across profiles unexpectedly.

## Still open / needs route-level verification

- Plugin enable/disable and runtime plugin rescan: Electron/local plugin authority versus backend plugin discovery/readback.
- Custom endpoint create/update/delete and `makeDefault`: REST response/readback and secret handling.
- Model settings auxiliary/MoA/fallback controls: profile config write/readback and provider/model validation.
- Cron create/edit/run/pause/resume controls: scheduler authority, task identity, delivery target and readback.
- Webhook create/update/enable/delete controls: backend route, secret redaction, enable-state readback and rollback.
- Billing/payment controls: external provider authority; never treat local UI success as payment success.
- Profile create/rename/switch controls: profile authority, re-home semantics and session isolation.
- Gateway/remote connection controls: Electron machine authority plus backend auth/session binding.
- Memory provider selection: provider authority, active-provider readback and restart/session behavior.
- Desktop automation/Faber/Opus controls: no live per-user principal and role/provider binding is proven yet; keep gated.

## Classification rule for remaining controls

```text
LOCAL_BY_DESIGN
  no backend write; local presentation/preference only

CONNECTED
  authoritative route exists; scope, readback and failure behavior verified

UNWIRED
  user intent exists but no authoritative route is found

BLOCKED
  route exists but identity/capability/owner/production gate is unresolved

EXTERNAL_GATE
  external service owns final result; UI may show pending/confirmed/failed only
```

## Current gate

The inventory is **not complete**. The next control group is custom endpoints and profile/provider settings, followed by cron/webhooks. No control should be promoted to `CONNECTED` from a click handler alone; the backend result and readback must be exercised.
