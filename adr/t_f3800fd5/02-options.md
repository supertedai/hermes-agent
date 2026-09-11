# Options

1. Normalize only in conversation_loop.py. Rejected: too late; other budget arithmetic and telemetry can still receive strings.
2. Coerce every value silently with int(). Rejected: malformed values would be hidden and could create unsafe budgets.
3. Normalize at cron config/runtime boundary, accept positive ints and decimal strings, default only when absent, hard-fail invalid values. Chosen: fixes the source path while preserving fail-closed behavior.
