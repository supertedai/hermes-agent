# ADR-HERMES-SURFACE-BACKPLANE-001 — Web and Desktop as shared-backplane surfaces

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`
**Parent:** `CAD-HERMES-SURFACE-BACKPLANE-001`

## Decision

`.14` web GUI, PC/laptop Desktop, TUI and gateway use a common canonical auth/session and Hermes engine route. Their UI state is a projection; the backplane owns cross-surface session/event continuity.

The architecture distinguishes:

```text
surface visibility
≠ session identity
≠ backend authority
≠ writer readiness
≠ runtime effect
```

No surface may infer backend authority from a successful login alone.

## Web/Desktop migration decision

Keep the existing web GUI as the operational baseline until `BL-HERMES-SURFACE-BACKPLANE-001` and P1 thread parity are complete. Do not use a frontend replacement to work around an unresolved broker/session authority split.

The Desktop front layer is a later strangler/canary migration over the same backend contracts, not a new auth, session or memory system. Cutover requires parity, health, compatibility and rollback receipts.

## Consequences

- one user can move between web, Desktop and laptop without separate memory silos;
- all learning and memory events enter through Hermes and canonical ingest;
- local/offline queues require idempotency and explicit replay status;
- surface drift is visible as `STALE`, `DIVERGED` or `UNKNOWN`;
- a known-good Desktop remains the rollback baseline.

## Rejected alternatives

- independent `.14` memory database;
- separate web-only learning writer;
- direct Desktop-to-graph writes;
- treating login success as authority proof;
- destructive migration of the existing Desktop/session baseline.

Runtime activation remains gated by `BL-HERMES-SURFACE-BACKPLANE-001`.

## 2026-08-10 topology convergence note (Symbiose BL-4023)

A per-session surface block now runs on the Hermes Opus memory provider, reporting: surface,
surface confidence, serving process, platform, principal, home and profile — plus an explicit
"not distinguishable from here" field for the browser-on-phone vs browser-on-PC case.

**The prompt-block renderer in `agent/mwp_topology_context.py::render_context()` has NO
CALLERS.** Measured: the only consumers of that module are
`agent/mwp_world_model_topology.py` (`project_topology_context`) and
`scripts/mwp_closeout_tick.py` (`load_topology_context` against
`docs/mwp-local-topology-readback.json`); no `agent/*.py` references `system_prompt` or
`prompt_block`. The module is deployed and the readback file is fresh, but the renderer is
written, not wired. This note therefore records a convergence OPPORTUNITY, not a duplicate in
operation — BL-4023 is the first thing on this axis that actually reaches a system prompt.
Adopting an unwired vocabulary because it was written first would be cargo cult, not
convergence.

**The two confidence axes measure different things and both are needed.**
`classify_topology_status()` yields `LIVE / STALE / DRIFTED / UNKNOWN` from `freshness.status`
(a TTL comparison against `recorded_at`) and `drift.added/removed/changed` — properties of a
CACHED SNAPSHOT of host inventory. `_topology()` is computed live in-process with no snapshot
and no TTL, and its axis (`sikker` / `utledet` / `meldt av klient` / `ukjent`) expresses the
BASIS FOR THE INFERENCE. Forcing the latter onto the former would mean emitting `LIVE`
unconditionally: nothing is cached, so it can never be STALE, and there is no inventory to
diff, so it can never be DRIFTED. Four meaning-bearing values would collapse into one constant.
That is a category error, and it is the reason the axes are not merged here.

**Coverage against the seven required topology-binding fields: three of seven, and the next
two sit behind ONE named wire change.**

| field | status |
|---|---|
| `principal_id` | available — resolved per turn |
| `session_id` | available — threaded by `initialize()` |
| `conversation_id` | available in practice — the session id IS the conversation id on this path |
| `device_id` | MEASURED ON `.14`, never forwarded (cookie `opus_device_id`) |
| `login_surface_id` | MEASURED ON `.14`, never forwarded (request Host header) |
| `installation_id` | does not exist anywhere |
| `tenant_id` | does not exist anywhere |

The two middle rows are the same finding as `device_class`: same proxy, same missing wire,
same `_stamp_prompt_identity` that carries only `user_id` into `prompt.submit`. One `.14`
change — stamping `device_id`, `login_surface_id` and `device_class` the way `user_id` already
is — would deliver three of the gaps at once. The remaining two are absent by construction and
are NOT stubbed: emitting seven fields where five are `null`, under a status that always reads
`LIVE`, would be an empty drawer painted green. Named here instead.
