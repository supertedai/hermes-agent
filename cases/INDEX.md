# MWP-UOSH-001 — Case index

This directory is the case-level execution index for the MWP workspace.

## Operating rule

- One active case at a time.
- Each case gets its own folder and `CASE.md`.
- Every case references `MWP-UOSH-001`.
- Every case records preflight, scope, risks, evidence, tests, readback, rollback and closeout.
- GUI Project is the workspace/index; Kanban is the planned canonical durable task authority.
- If a separate chat thread is opened manually, bind it to the case ID in its first message.

## Cases

| Case | Scope | Status | Folder |
|---|---|---|---|
| `CASE-AUTONOMY-00` | Autonomy Control Plane foundation | FOUNDATION SUBPACKAGE CLOSED / role-provider owner gate; parent open | `autonomy-00-control-plane/` |
| `CASE-IDENTITY-01` | Desktop → `/brukere` principal/session binding | BLOCKED / remote identity route gap | `identity-01-desktop-auth/` |
| `CASE-DESKTOP-01` | Desktop single pane of control | OPEN / architecture gate | `desktop-01-control-plane/` |
| `CASE-SYMBIOSE-02` | Graph/Qdrant/GNN integrity and provenance | AUDIT COMPLETE / shadow repair blocked | `symbiose-02-graph-vector-gnn-integrity/` |
| `AUTOMATION-01` | MWP task/evidence/worktree integration | AUTHORITY UNVERIFIED / Kanban bootstrap blocked | `../docs/mwp-uosh-automation-01-preflight.md` |

## Dependency order

```text
CASE-AUTONOMY-00
  └── CASE-IDENTITY-01
        └── Kanban/task authority
              └── evidence/orchestrator
                    ├── CASE-SYMBIOSE-02 (graph/Qdrant/GNN integrity)
                    └── Desktop control plane
```

## Next permitted case

`CASE-AUTONOMY-00` is the foundation discovery case. It may define/read/test contracts, but cannot activate workers or writes until `CASE-IDENTITY-01` and its authority gates are resolved.
