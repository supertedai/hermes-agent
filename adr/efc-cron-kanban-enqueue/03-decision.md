# Decision

Implement `hermes kanban enqueue <title>` as an idempotent upsert using the existing Kanban DB. A non-archived row with the key is updated in place for title/body/assignee/priority and re-queued when it is terminal (`done`, `blocked`, or `review`); a running row is not disturbed. A missing row is created as `ready` (or `todo` when parents gate it). The command emits JSON or a concise id/status and exits; it never claims or spawns.

The existing dispatcher remains responsible for atomic claim/lease, worktree resolution, subprocess creation, and `HERMES_KANBAN_TASK`, `HERMES_KANBAN_BOARD`, and DB/workspace environment injection.
Status: implemented pending tests/review.
