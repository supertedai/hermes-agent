# Closeout

Implemented in Hermes fork worktree `wt/t_9c6375ea` from `origin/main` 056547bd98. Added `hermes kanban enqueue` and `kanban_db.enqueue_task`; repeated keys refresh one active card, terminal cards re-enter `ready`, running claims are preserved, and enqueue can route a new card to an explicit worktree/project anchor. Added deterministic tests covering idempotency, update, terminal requeue, running-claim preservation, and dispatcher claim/spawn environment injection.

Observed verification: focused enqueue/dispatcher tests passed (4 passed); `git diff --check` and Python compileall passed. No cron jobs.json or public HTML files were modified. Luna second-opinion route was attempted but unavailable due to missing OpenAI key; this is explicitly non-independent/unverified. Runtime apply and merge remain human-gated.
