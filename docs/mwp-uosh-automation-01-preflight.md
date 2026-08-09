# MWP-UOSH-001 / AUTOMATION-01 — Preflight and bounded scope

## Classification

- Parent: `MWP-UOSH-001`
- Case: `AUTOMATION-01`
- Change class: orchestration integration
- Planned blast radius: `R1` initially; escalate to `R2+` if scheduler/runtime wiring is added
- Current mode: isolated worktree, discovery/planning only
- Target branch: `mwp/uosh-automation-01`
- Base: `ca939c488068407fcbbfc97165b989cccf52c3db`

## Objective

Connect MWP task/case identity and evidence references to existing Hermes workflow primitives without creating a parallel scheduler, evidence store, runtime owner, or memory store.

## Reuse targets

- `agent/code_workflow.py`
  - `PreflightGate`
  - `FaberGoal`
  - `FaberGoalRegistry`
  - `GoalState`
  - `ReviewVerdict`
  - `StepJournal`
  - `FailureClass`
- `agent/verification_evidence.py`
  - `verification_events`
  - `verification_state`
  - classified command evidence
- existing kanban/worktree isolation
- existing cron scheduler only as a later adapter; no scheduler activation in this case

## Non-goals

- No new cron job or scheduler activation.
- No new core memory store.
- No graph/Qdrant/GNN write.
- No production runtime change.
- No change to the dirty main worktree.
- No automatic ADR/BL creation.
- No bypass of owner/reviewer gates.
- No assumption that a successful worker call is closeout evidence.

## Current preflight

- Repository has substantial tracked and untracked work in the main worktree.
- Main worktree is not a safe patch target.
- Isolated worktree was created for this case.
- Existing ADR/BL authority for a new MWP orchestrator is not yet established.
- Test baseline could not run from the active gateway context; pytest execution must happen from a separate runtime.
- Web surface `https://ai.byopus.com/` is not part of this bounded patch and remains separately unverified.

## Existing canonical-task candidate

Existing Hermes Kanban already provides the primitives needed for MWP task authority:

- `project_id` and board scoping;
- parent/child task links and cycle checks;
- dependency readiness/recompute;
- claims, leases, heartbeats and stale-claim recovery;
- worker PID/run state and bounded runtime;
- retry/failure circuit breaker;
- goal-mode continuation;
- session ID, result, attachments and event history;
- per-task worktree/branch resolution and isolation;
- dispatch and worker lifecycle.

Decision required: use Kanban as the canonical MWP task/case state authority and treat the GUI Project as the human-facing workspace/index. Do not introduce a second MWP task database unless an accepted ADR proves Kanban cannot carry the required fields.

## Proposed bounded interface

The first implementation, if authority is confirmed, may add only an adapter that:

1. accepts `mwp_id`, `case_id`, `task_id`, parent task IDs and dependency IDs;
2. maps them to existing goal/workflow state without duplicating storage;
3. carries CAD/ADR/BL references and owner-gate status;
4. attaches evidence references from the existing verification ledger;
5. emits a structured metadata-only master readback;
6. refuses to advance a parent when dependencies are not closed;
7. remains side-effect free until a separate execution adapter is approved.

## Acceptance criteria

- Every MWP task record has stable `mwp_id`, `case_id` and `task_id`.
- Parent/child dependency state is explicit.
- Existing `FaberGoalRegistry` remains the authoritative goal store for Faber goals.
- Existing verification evidence remains the authoritative command-evidence ledger.
- No duplicate evidence store is created.
- A blocked or owner-gated child cannot advance its parent.
- Metadata-only readback contains status, evidence references, blockers and next permitted action.
- Existing current behavior is unchanged outside the isolated adapter.
- Syntax/static checks pass in the isolated worktree.
- Runtime tests execute from a separate test environment before any closeout claim.

## Gate

```text
CURRENT VERDICT: CANONICAL AUTHORITY IDENTIFIED / OPERATIONAL BOARD UNVERIFIED
```

Read-only readback confirms that existing Hermes Kanban is the intended canonical
implementation surface (`~/.hermes/kanban.db` plus `tools/kanban_tools.py`). SQLite
integrity is `ok` and the task/run/event/link schema is present, but the live local
database has zero tasks, runs and events. MWP task state is therefore not
operationally instantiated here. No second MWP task store is created.

The role/provider declaration is also partial: the active config declares
Luna/Claude reference models, but the default model/provider pair and delegation
model do not constitute verified Sol/Luna/Claude role bindings. That remains an
explicit runtime/owner gate.

Receipt: `docs/mwp-kanban-authority-readback-v1.json`.

## Rollback

Delete/revert only the isolated adapter and this case artifact. Do not reset, clean or overwrite the main worktree. Do not modify existing goal, evidence, memory, graph, Qdrant or scheduler state.

## Evidence required for closeout

- isolated diff and file list;
- CAD/ADR/BL authority readback;
- separate-runtime test output;
- evidence-ledger readback;
- dependency/parent-block test;
- metadata-only master readback;
- reviewer verdict;
- rollback verification.
