# Decision

Add a small cron boundary resolver. It returns the default 500 only for a missing/None value, returns positive ints for int or surrounding-whitespace decimal-string input, and raises ValueError for booleans, zero/negative values, non-integral types, or malformed strings. The scheduler calls it before constructing the agent.

Status: proposed until tests and review complete.
