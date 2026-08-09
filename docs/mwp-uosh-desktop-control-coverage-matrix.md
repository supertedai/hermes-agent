# MWP-UOSH-001 — Desktop control coverage matrix

**Status:** PARTIAL / VERIFIED SLICES + EXPLICIT OPEN GATES
**Scope:** Hermes Desktop control/readback plane
**Authority rule:** Desktop renderer is never authoritative for backend-owned state.

## Status vocabulary

- `CONNECTED` — authoritative route and readback are verified.
- `CONNECTED_READ_ONLY` — backend status is read; no mutating control is exposed.
- `CONNECTED_GATED` — route exists, but irreversible/production action remains gated.
- `LOCAL_BY_DESIGN` — Electron/renderer owns the state by declared scope.
- `EXTERNAL_GATE` — external provider owns final result; Desktop shows lifecycle only.
- `BLOCKED_UNWIRED` — capability exists elsewhere, but no safe Desktop route is verified.
- `BASELINE_BLOCKED` — verification is blocked by unrelated existing test/runtime errors.

## Verified coverage

| Surface/control | Authority | Route/implementation | Principal/scope | Readback | Rollback/stop | Evidence/status |
|---|---|---|---|---|---|---|
| Settings config autosave | Hermes backend config | `PUT /api/config` then `GET /api/config` | active profile | normalized config record | stale generation guard; error remains visible | targeted UI tests; `CONNECTED` |
| Main model/profile default | Hermes model assignment/config | `setModelAssignment(scope=main)` or config PUT | profile | assignment response + config refresh | profile epoch/generation guard | model-settings tests; `CONNECTED` |
| Active session model | Hermes session | gateway `config.set` with `session_id` | runtime session | session event/deferred response | optimistic rollback on failure | model-controls tests; `CONNECTED` |
| Reasoning/fast | Hermes session/profile config | session `config.set` or profile config | session/profile | returned config/session state | rollback + stale generation | model controls; `CONNECTED` |
| Auxiliary models | Hermes auxiliary assignment | `setModelAssignment(scope=auxiliary)` | profile/task slot | auxiliary response/refresh | stale-slot warning; explicit reset | model-settings tests; `CONNECTED` |
| MOA presets | Hermes MOA config | `saveMoaModels` | profile | saved response; complete-slot validation | generation guard; incomplete state held | model-settings tests; `CONNECTED` |
| Fallback models | Hermes profile config | config autosave | profile | authoritative config GET | stale generation guard | config/settings tests; `CONNECTED` |
| Active memory provider | Hermes profile config/Symbiose provider | config autosave + provider status route | profile/user scope | config/provider status | backend error; no local success claim | config/provider coverage; `CONNECTED` |
| Memory provider config | provider backend | provider config PUT/GET | profile/provider | field-level or modal refresh | failed write remains visible | provider panel/modal; `CONNECTED` |
| Memory provider OAuth | provider OAuth backend | start + status polling | profile/provider | terminal OAuth status | timeout/error/cancel | provider connect flow; `CONNECTED` |
| Custom endpoints | Hermes endpoint authority | create/update/validate/activate/delete API | profile | response endpoint list | failed mutation keeps form; explicit delete | endpoint coverage; `CONNECTED` |
| Profiles | Hermes profile authority | create/rename APIs | local profile scope | parent list refresh/select | dialog remains open on error | profile dialogs; `CONNECTED` |
| Cron | Hermes scheduler | cron create/update/delete/pause/resume/run API | profile/job/principal | query/store/run-state refresh | pause/stop/error paths | cron tests; `CONNECTED` |
| Webhooks | Hermes webhook backend | enable/create/delete/toggle API | profile/webhook | query invalidation + restart status | restart-needed/error path | webhook tests; `CONNECTED` |
| Gateway connection | Electron + real backend WS/auth | connection IPC + WS ticket/token | global or profile connection | saved config + real WS state | reconnect/backoff/reauth escalation | 143 Electron tests; `CONNECTED` |
| Approval mode | Hermes config/session | `config.get/set approvals.mode` | profile | confirmed mode response | revert to confirmed mode | approval tests; `CONNECTED` |
| Session/global YOLO | Hermes config/session | scoped `config.set yolo` | session/global | returned value | backend error; no false success | YOLO path; `CONNECTED` |
| Kanban orchestration | Kanban backend | plugin API mutations | board/project/task | query invalidation | mutation error; dispatcher gates | Kanban route audit; `CONNECTED` |
| Goals | Hermes session | `slash.exec goal status` + events | runtime session | goal event/status readback | no renderer execution authority | goals tests; `CONNECTED_READ_ONLY` |
| Maintenance | Hermes action API | doctor/audit/backup/curator/memory actions | profile/principal | action polling/logs/status | bounded polling/error | maintenance implementation; `CONNECTED` |
| Review/ship pane | Electron/local Git | typed Git review bridge | repo/cwd/session | status/diff/ship state | explicit commit/push gate | review tests; `CONNECTED_GATED` |
| Billing/usage read | billing provider/API | billing query routes | external account | provider response/refresh | read-only | billing tests; `CONNECTED` |
| Credits/payment/auto-reload | external billing provider | charge/settlement/portal flow | external account/principal | settlement poller | ambiguous/retry/step-up/portal | billing tests; `EXTERNAL_GATE` |
| Desktop plugin lifecycle | Electron/Desktop loader | local loader handles + decision store | window/profile/Desktop install | loader status/handles | deactivate; local error | local authority; `LOCAL_BY_DESIGN` |
| Model visibility/layout/presentation | renderer/Desktop | nanostores/local storage | profile/window preference | local store | local reset | declared local preference; `LOCAL_BY_DESIGN` |

## Open gates

| Capability | Existing backend candidate | Missing contract | Status |
|---|---|---|---|
| Desktop Faber/Opus execution | `FaberRuntime`, `FaberGoalRegistry`, `GovernedCodeRunner`, loopback `/api/internal/tui/emit` | typed Desktop route, principal/capability, role/provider resolver, Kanban lease, reviewer PASS, evidence/readback, rollback | `BLOCKED_UNWIRED` |
| Desktop Faber goal control | Faber goal registry exists | safe read-only catalog route and owner/principal binding | `BLOCKED_UNWIRED` |
| Live Sol/Luna/Claude binding | config has models/providers, but no role binding | runtime resolver evidence and role receipt | `BLOCKED_UNWIRED` |
| Full Desktop check | TypeScript suite | five preview-routing baseline errors | `BASELINE_BLOCKED` |
| Full ASI plane | Hermes/Symbiose/graph/Qdrant/GNN/learning surfaces | complete source→runtime→readback matrix | `OPEN` |

## Required Faber Desktop route contract

No renderer button should call the internal relay directly. A future typed route must carry and verify:

```text
principal_id
profile
client_session_id
durable_session_id
mwp_id
case_id
kanban_task_id
faber_goal_id
requested_role
model/provider receipt
scope
capability
owner/governance gate
reviewer gate
rollback reference
```

The route must return metadata-only state:

```text
accepted | blocked | queued | running | reviewing | landed | failed
next_permitted_action
gate
blocker
evidence_refs
readback
```

It must not expose raw memory, secrets, code history or internal relay credentials to the renderer.

## Current conclusion

The Desktop control plane is mostly wired to existing authorities. The remaining high-risk gap is not an unconnected cosmetic button; it is the governed Faber/Opus execution boundary. That boundary stays blocked until the typed route and identity/reviewer/evidence contract exist.
