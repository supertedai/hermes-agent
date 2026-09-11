# Charter

- Change: Normalize cron iteration budget at the cron/runtime boundary.
- Owner: Hermes cron/runtime maintainers; task t_f3800fd5.
- Scope: cron scheduler resolution and focused regression tests only.
- Exit criterion: int and numeric-string budgets reach AIAgent as ints; missing config uses the documented default; invalid configured values fail before provider execution with a clear error; focused tests and read-only synthetic smoke evidence exist.
- Human gate: review and landing remain human-controlled.
