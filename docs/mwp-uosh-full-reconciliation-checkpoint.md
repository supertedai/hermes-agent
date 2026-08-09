# MWP-UOSH-001 — Full reconciliation checkpoint

**Status:** INCOMPLETE / RECONCILIATION IN PROGRESS
**Date:** 2026-08-06
**Mode:** read-only audit; no fetch, merge, reset, push, graph write, Obsidian write, or runtime restart.

## Source priority

1. Direct live probe/readback.
2. Canonical registry/manifest and actual source files.
3. Tests that exercise the behavior.
4. Documentation/source references.
5. Worker summaries only as leads; contradictory summaries are not accepted as evidence.

## Directly verified

### Git

- Main source target: `/home/agent/agent-layer/hermes-agent`.
- Main branch at session start: `jetstream-plugin`; main worktree is dirty with tracked and untracked changes.
- Isolated reconciliation branch: `mwp/uosh-automation-01` at base `ca939c488`.
- Isolated worktree: `/home/agent/agent-layer/mwp-uosh-automation-01`.
- Isolated worktree contains untracked audit artifacts under `docs/`; this is intentional and must not be confused with main-worktree status.
- Remotes locally known:
  - origin: `https://github.com/supertedai/hermes-agent.git`
  - upstream: `https://github.com/NousResearch/hermes-agent.git`
- No fetch/merge/reset/clean/push was performed.

### CAD

- Canonical local CAD index: `/home/agent/agent-layer/symbiose-workspace/ASI_CAD_V0.1/README.md`.
- CAD set contains 36 Markdown files: CAD-0 and CAD-A through CAD-Å/Ø.
- Roadmap: `/home/agent/agent-layer/symbiose-workspace/ASI_CAD_ROADMAP_V0.1.md`.
- Roadmap status contract is source→registry→enabled→schema→reachable→instantiated→readable→measured→validated→gated→promoted.
- `ROADMAP-0.md` explicitly says the runtime manifest and full source-to-runtime matrix are not complete.

### BL/ADR

- No dedicated `.bl`/`.adr` file extension registry was found by the worker glob. This does **not** mean no BL/ADR exists.
- Actual source/docs contain BL/ADR references, including BL-2290, BL-2363, BL-2653, BL-2783/2786/2789, BL-2790, BL-3254, BL-3404, BL-3428, BL-3432, BL-3621, BL-3664, BL-3684, ADR-022, ADR-035, ADR-038, ADR-045 and ADR-046.
- These references are not yet a canonical full registry with owner, adoption, freshness and closeout reconciled.

### Local user/Symbiose surfaces

- `http://localhost:9119/brukere` returned HTTP 200.
- `http://localhost:9119/symbiose` returned HTTP 200.
- `/brukere` maps to `hermes_cli.dashboard_auth.user_store` and canonical users/capability policy.
- `/symbiose` is an existing Symbiose UI/service surface; its internal plugin API is auth-gated (401 without auth).

### .40 topology

Bounded probes found:

- `.11`: SSH/22 and TCP/8000; service on 8000 unknown.
- `.12`: SSH/22, nginx/80, router-error/8000, unified_api/8010, cAdvisor/8080.
- `.13`: SSH/22, unified_api/80, unified_api/8000, nginx/8080.
- `.14`: SSH/22 and TCP/9101; service unknown.
- `.15`: local host with SSH/22, 8210, 8642, 9101 and local Hermes dashboard 9119.

`.12:8010` root returned `{"status":"ok","service":"unified_api","docs":"/docs","health":"/health"}`.

## Not reconciled yet

- Canonical BL/ADR registry, owners, adoption/freshness and closeout state.
- Full mapping from all 36 CAD files/components to MWP tasks and runtime evidence.
- `.12` versus `.13` service ownership/primary-replica/runtime-role relationship.
- Authenticated graph readback, graph writer, Qdrant collections/points and GNN checkpoint/owner.
- Obsidian vault path/owner/live readback on `.13`.
- Complete remote Git refs and branch divergence (no fetch was performed).
- Complete MWP-task coverage: every task still needs active/historical/stale/conflict/unmapped/owner-gate/verified classification.

## Worker-report discrepancies

- A worker reported “no BL/ADR/CAD files” after searching only extension patterns. This is downgraded because actual source/docs contain extensive textual BL/ADR references and the CAD manifest is present.
- A worker reported `.13` unavailable. Direct bounded probes from this session observed `.13:80` and `.13:8000` returning unified_api roots; endpoint availability may vary by route/time, so role/status remains unresolved rather than marked down.
- A worker reported no current changes in its audited worktree; the isolated branch intentionally contains untracked reconciliation artifacts. Main dirty status remains separately preserved.

## Collision verdict

```text
MWP-UOSH-001 may remain a work-package reference.
No new BL/ADR/CAD identifier is minted.
No live adapter or new store/writer/scheduler is authorized.
Full reconciliation is NOT CLOSED.
```
