# Verification

Observed 2026-09-11 in the isolated worktree:

- `./scripts/run_tests.sh tests/cron/test_scheduler.py -k 'normalizes_string_iteration_budget_before_agent_init' -v`: 1 passed. This executes `run_job`, loads a temporary config containing `agent.max_turns: '17'`, constructs the patched `AIAgent`, and asserts the received `max_iterations` is the integer `17`.
- `./scripts/run_tests.sh tests/cron/test_iteration_budget_config.py tests/cron/test_scheduler.py tests/cron/test_cron_inactivity_timeout.py tests/gateway/test_cached_agent_max_iterations.py -v`: 81 passed, 0 failed.
- Resolver coverage retains integer, numeric-string, missing/default, boolean, non-positive, fractional, empty, and malformed values; invalid values still raise `ValueError` before agent construction.

The synthetic smoke test is read-only and uses mocked provider/session seams. Production cron execution_success for cron-sundhetsvakt and kjede-læring, plus delivery-route/status readback, remain unresolved until a human applies the reviewed commit on the authoritative Hermes host. No claim is made for those gates here.
