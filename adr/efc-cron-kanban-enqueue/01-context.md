# Context

Observed in Hermes fork at origin/main (commit 056547bd98): `hermes kanban create` already stores an idempotency key, and the embedded dispatcher already owns claim, workspace resolution, subprocess spawn, and task environment injection. Existing create semantics return an existing non-archived task without updating it.

The requested cron boundary is enqueue-only. The dispatcher must remain the only component that claims/leases and spawns. No runtime cron state is changed by this repository change.

Unknowns: the exact production cron prompt/schedule and EFC HTML acceptance harness are outside this fork and are intentionally not modified here.
