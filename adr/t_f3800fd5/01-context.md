# Context

Observed task evidence reports TypeError when the conversation loop compares an int API call count with a string max_iterations or string iteration_budget.remaining. Current code in cron/scheduler.py reads agent.max_turns directly with `or`, then passes the value into AIAgent; agent/agent_init.py stores it unchanged and constructs IterationBudget from it. The loop compares both values at conversation_loop.py:1316.

Boundary: config.yaml -> cron scheduler -> AIAgent initialization -> conversation loop. Unknown before implementation: which exact persisted config value caused the reported production incident and whether all affected jobs share one malformed value.
