# CASE-AUTONOMY-00 — Live 13-step entrypoint readback

**Mode:** read-only
**Date:** 2026-08-06
**Target:** local active runtime / `$HERMES_HOME=/home/agent/.hermes`

## Active processes observed

```text
/home/agent/agent-layer/hermes-agent/.venv/bin/python -m hermes_cli.main gateway run
/home/agent/agent-layer/hermes-agent/.venv/bin/python3 /home/agent/.local/bin/hermes serve --isolated ...
/home/agent/agent-layer/hermes-agent/.venv/bin/python3 -m hermes_cli.main dashboard --no-open ...
/usr/bin/node .../ui-tui/dist/entry.js
/usr/bin/python3 /home/agent/agent-layer/symbiose-workspace/luna_proxy.py
```

These prove active Hermes/dashboard/TUI/Luna-proxy processes only. They do not prove the 13-step Autocoder sequence is invoked.

## Active cron inventory

`/home/agent/.hermes/cron/jobs.json` contains two enabled jobs:

```text
5b12cb36bb46  cyber-detector-watchdog  */30  no_agent script
24764d5a330a  ecowitt-weather-watchdog */30  no_agent script
```

Latest output at `2026-08-06 09:30:18` is silent/empty for both. Neither job declares a model, skill, workflow, Autocoder wrapper, reviewer or Faber route.

## Wrapper search

Read-only search found:

- canonical 13-step skill: present;
- `agent/code_workflow.py`: present;
- `ContinuousPipeline`/`PipelineAdapter`/Autocoder executable wrapper in target repo or `$HERMES_HOME`: not found;
- 13-step cron/launch definition: not found;
- explicit live Sol/Luna/Claude role resolver for the 13-step chain: not found.

## Verdict

```text
13-step normative workflow: FOUND
Deterministic code rails: FOUND
Hermes/Faber/Symbiose processes: LIVE
13-step live wrapper entrypoint: UNVERIFIED / NOT FOUND
Autocoder fully active: NO CLAIM
```

## Next permitted action

Design a thin, read-only MWP entrypoint adapter that calls the existing 13-step semantic stages and existing `GovernedCodeRunner`/reviewer/evidence rails. It must first run dry-run/read-only and emit a durable `case_id/task_id` receipt. It must not activate a scheduler, commit, land, deploy, or write graph/memory/Qdrant.
