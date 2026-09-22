# Charter

Request: add a Git-backed Hermes CLI entry point for cron job 436e52f74907 to idempotently enqueue/update one EFC maintenance card, then stop.
Owner: Morten; implementation: kanban worker t_9c6375ea.
Scope: Hermes Kanban CLI/database only; dispatcher remains the sole claimant and worker spawner.
Exit criterion: deterministic tests prove repeated enqueue does not duplicate, updates the existing card, and leaves dispatch ownership to the existing claim/spawn path.
Out of scope: editing ~/.hermes/cron/jobs.json, runtime apply, public HTML, or EFC maintenance logic.
Status: proposed before implementation.
