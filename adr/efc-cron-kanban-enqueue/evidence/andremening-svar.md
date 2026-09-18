Warning: Unknown toolsets: none
Stance: not supported as written; the design is salvageable, but there is at least one likely production-blocking state bug and several unverified concurrency and lifecycle assumptions.

Findings

1. Severity: critical — newly created tasks appear to be created in the wrong state

Concrete mechanism:
`enqueue_task()` calls `create_task(..., initial_status="running")`, although enqueue is explicitly not allowed to claim, lease, create a worktree, or spawn a worker. If the dispatcher only claims `ready` tasks, every newly created task is stranded in `running` without a worker or claim.

This is especially serious because the stated warning only covers missing assignees. A task with a valid assignee could still be permanently undispatched.

Evidence needed:
- The dispatcher’s exact eligibility query and state-transition code.
- A clean-database test asserting that a newly enqueued task is immediately dispatchable.
- Database inspection after enqueue: status, claim lock, lease, worker PID, and subsequent dispatcher behavior.

What would change my mind:
Evidence that `running` is a dispatchable pre-claim state and that the dispatcher transitions such rows into claimed execution without requiring an existing claim. That would be unusual and would need to be documented explicitly.

2. Severity: high — the “running rows are left alone” rule can preserve orphaned work forever

Concrete mechanism:
The code leaves every existing `running` row in `running`, not only running rows with a valid claim. The contract specifically mentions “a running row with claim” but the implementation does not distinguish that case. A crash, partial transaction, manual database edit, or old bug could leave a running row with no valid claim, lease, or worker. Re-enqueue would not recover it.

Evidence needed:
- The definitions of a valid claim: claim lock, lease expiry, worker PID, and worker heartbeat.
- The dispatcher’s behavior for `running` rows without a claim.
- Tests for enqueue after worker death, expired lease, and missing claim metadata.

What would change my mind:
A database invariant proving every `running` row necessarily has a live claim, plus recovery logic that handles expired claims independently of enqueue.

3. Severity: high — terminal requeue may leave stale execution metadata

Concrete mechanism:
For `done`, `blocked`, or `review`, the code changes only `status` and possibly `completed_at`. It does not visibly clear claim locks, lease timestamps, worker PID, worktree metadata, or other terminal-state fields. If the dispatcher uses any of those fields when deciding whether a `ready` task can be claimed, the refreshed task may remain unclaimable or may look as though an old worker still owns it.

Evidence needed:
- The complete task schema.
- All fields consulted by claim and lease recovery.
- Tests requeueing terminal rows populated with realistic claim and worker metadata.

What would change my mind:
A schema invariant or dispatcher query demonstrating that terminal rows cannot retain claim metadata, or explicit cleanup in the state transition.

4. Severity: high — the list-then-create race still violates the advertised uniqueness contract

Concrete mechanism:
Two callers can both execute the `SELECT`, observe no active row, and then both create a row. The function therefore does not guarantee “one row per producer-supplied key.” The existing race in `create_task` remains on the new path.

A single producer reduces the probability but does not eliminate it: retries after timeout, overlapping cron/systemd invocations, duplicate timer delivery, manual reruns, or two processes spawned during deployment can overlap.

Evidence needed:
- A concurrent stress test with two or more processes enqueueing the same key.
- The transaction boundaries inside `create_task`.
- Existing duplicate-key counts in production databases.
- Whether SQLite is configured with WAL, busy timeouts, and suitable locking behavior.

What would change my mind:
A database-enforced uniqueness constraint, or an equivalent atomic insert/upsert that makes the invariant true under concurrent writers.

5. Severity: high — the uniqueness scope is underspecified, and archived rows create ambiguity

Concrete mechanism:
The lookup excludes archived rows. Thus the implementation permits a new active row with a key previously used by an archived row. That may be intentional key reuse, but it is not literally “one row per key.” It also raises ambiguity if multiple historical rows exist: the newest non-archived row is selected, while older duplicates remain.

A global key can also collide between unrelated producers unless the key namespace includes producer identity.

Evidence needed:
- The intended lifecycle of idempotency keys after archival.
- Whether keys are globally scoped or scoped by producer/project.
- A migration audit for existing duplicate keys.
- The archival and retention rules.

What would change my mind:
An explicit contract saying keys are reusable after archival and are globally namespaced, with database constraints enforcing exactly that policy.

6. Severity: high — concurrent refreshes have last-writer-wins behavior with no ownership or version check

Concrete mechanism:
Two producers can select the same row and then overwrite title, body, assignee, or priority in an arbitrary order. Optional fields make this worse: one producer can unintentionally preserve values written by another, while another can overwrite them later. There is no producer identity check, revision number, compare-and-swap condition, or event ordering.

Evidence needed:
- Whether multiple producers can share a key.
- Concurrent update tests with conflicting payloads.
- The intended owner of each idempotency key.
- Whether event timestamps or revisions are used downstream.

What would change my mind:
A documented single-writer guarantee per key, enforced operationally or in the database, or optimistic concurrency with a revision/producer check.

7. Severity: medium-high — “omitted means keep” is unsafe as the only producer-facing semantics

Concrete mechanism:
This is reasonable for a PATCH-like administrative update, but periodic producers usually express desired state, not a partial human edit. If a producer previously supplied an assignee, body, or priority and then stops supplying it because of a bug, the old value silently persists. The task can continue to target an obsolete assignee or carry stale instructions indefinitely.

The current behavior also makes some corrections impossible: `None` means “keep,” so the producer cannot explicitly clear a body or assignee through this API.

What I would require:
- Separate operations, for example:
  - `enqueue` as declarative desired-state upsert, requiring all producer-owned fields;
  - `patch` as explicit partial update.
- Or an explicit field mask such as `--set-assignee`, `--clear-assignee`, and `--keep-assignee`.
- A producer/schema version and payload fingerprint stored with the task.
- Validation that required producer-owned fields are present on every periodic enqueue.
- Warnings or failures when a producer’s payload shape changes.
- Tests proving omitted, explicitly cleared, and defaulted values are distinct.

8. Severity: high — `review -> ready` can bypass human review and cause repeated work

Concrete mechanism:
A review task normally represents work completed by a worker and awaiting independent approval. A periodic producer that refreshes the same key can move it back to `ready`, causing the work to be dispatched again before review is resolved. This can bypass the review gate, create duplicate implementation attempts, or erase the operational meaning of “awaiting review.”

For a maintenance producer, this can happen every week: the producer repeatedly resurrects a card that a human intentionally left in review, producing churn and potentially multiple competing worktrees.

I would normally exclude `review` from automatic requeue. A safer default would be:
- `done -> ready` if recurring execution is intended;
- perhaps `blocked -> ready` only with an explicit retry policy;
- `review` remains in review unless an explicit force/requeue operation is requested.

Evidence needed:
- The state machine and meaning of `review`.
- Whether review is a terminal state or an intermediate gate.
- Examples of periodic cards intentionally being re-run while in review.
- Review/landing behavior when a card is requeued.

What would change my mind:
A documented rule that review is merely a terminal “last run completed” state, not a human approval gate, plus tests showing requeue is safe and does not bypass required review.

9. Severity: medium-high — `blocked -> ready` may create a hot loop against an unresolved external dependency

Concrete mechanism:
If a task is blocked by missing credentials, an unavailable service, a human decision, or a known repository problem, weekly enqueue will immediately make it ready again. The dispatcher can repeatedly claim and fail the same task, generating noise and consuming worker capacity.

Evidence needed:
- The meaning of `blocked`.
- Whether blocked tasks carry retry-after, failure reason, or backoff metadata.
- Dispatcher behavior for repeatedly requeued tasks.
- Production history of blocked maintenance cards.

What would change my mind:
A bounded retry/backoff policy, or a producer-specific rule that blocked tasks are only requeued when the blocking condition has changed.

10. Severity: medium — the implementation does not refresh all fields a producer may believe it owns

Concrete mechanism:
The stated refresh behavior covers title, body, assignee, and priority, but not `created_by`, `workspace_kind`, `workspace_path`, `branch_name`, or `project_id`. If those are part of the producer’s desired configuration, an enqueue silently leaves stale values. Conversely, if they are intentionally immutable, that needs to be explicit in the CLI contract.

There is also an asymmetry where a new task receives `priority=0` when omitted, while an existing task preserves its priority. That may be correct, but it is an implicit create-versus-update distinction.

Evidence needed:
- The full CLI help and field ownership specification.
- Tests covering every accepted enqueue option on both create and refresh.
- Whether workspace and project identity are immutable after creation.

What would change my mind:
A documented immutable/mutable field matrix and tests enforcing it.

11. Severity: medium — event/audit semantics may be incomplete

Concrete mechanism:
The existing-row path appends an `enqueued` event, but the create path appears to rely on `create_task` events and does not visibly emit the same event. Requeueing a terminal task also records only a generic event with `updated: true`; it may not capture the old state, new state, producer, payload version, or reason.

This makes it harder to explain why a reviewed or blocked task became ready and harder to audit producer behavior.

Evidence needed:
- Event schema and consumers.
- A complete event sequence for create, refresh, requeue, and concurrent enqueue.
- Operational requirements for reconstructing task history.

What would change my mind:
Evidence that `create_task` emits an equivalent event and that downstream tooling already derives the missing transition data.

12. Severity: medium — input normalization and error behavior need a contract

Concrete mechanism:
Existing titles are stripped, but the new-task path passes the original `title` to `create_task`. Keys are stripped before lookup, which is good, but whether stored keys and CLI values are consistently normalized should be tested. `int(priority)` can raise exceptions at the database layer or CLI boundary, and `_canonical_assignee(None)` must preserve the distinction between omitted and explicitly cleared.

Evidence needed:
- CLI parsing code.
- `_canonical_assignee` implementation.
- Tests for whitespace, aliases, invalid priorities, Unicode, and explicit clearing.
- Whether errors are user-readable and transaction-safe.

What would change my mind:
A CLI-level validation suite demonstrating consistent normalization and stable errors.

The observed evidence is insufficient for these risks

The five focused tests and the end-to-end run establish useful happy-path behavior: refresh, basic requeue, preservation of a claimed running row, and absence of spawning. They do not establish concurrency safety, correct initial dispatchability, stale-claim cleanup, review semantics, blocked-task backoff, migration correctness, producer ownership, or CLI field-mask behavior.

The unchanged 168-test failure set is evidence against broad regression in that particular environment, but the 20 environment-related failures reduce its sensitivity. It is not evidence that the new state transitions or concurrency properties are correct.

What would change my mind

I would reconsider the stance after seeing:

- A clean-database enqueue test proving the created row is `ready` or otherwise demonstrably dispatchable.
- Concurrent multi-process enqueue tests proving one active row per key.
- A database-enforced uniqueness policy and a migration/audit plan for existing duplicates.
- Explicit state-machine tests for `done`, `blocked`, `review`, running-with-claim, and running-without-claim.
- Tests with stale claim and worktree metadata.
- A documented distinction between declarative producer upsert and partial patch semantics.
- Producer ownership, key namespace, payload version, and retry/backoff rules.
- Dispatcher integration tests showing no worker is spawned by enqueue and that the next dispatcher cycle handles the resulting row correctly.

Confidence: high on the identified code-level concerns, especially the `initial_status="running"` contradiction and the remaining race. Medium on the lifecycle findings because the full schema, dispatcher query, and state-machine definitions were not provided.

I could not evaluate from the description alone:

- The dispatcher’s exact eligibility and claim logic.
- Whether `create_task` clears or initializes claim metadata.
- The complete task schema and database indexes.
- The meaning of `review` and `blocked` in the project’s formal state machine.
- CLI defaults and whether omitted flags can be distinguished from explicit clears.
- Existing duplicate-key data and deployment/migration procedures.

Most likely production failure in the next three months

New maintenance cards will be created with `status='running'` but without a claim or worker, and will silently never be dispatched. The weekly producer will report successful enqueue operations, while the board accumulates apparently active but abandoned tasks. The first confirmation should be a clean-database enqueue followed by inspection of status, claim fields, and the dispatcher’s next scan.

session_id: 20260918_101349_18cf1d
