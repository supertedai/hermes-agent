# Options

1. Add an `enqueue` CLI action backed by an atomic database upsert, reusing existing dispatcher behavior. Chosen: smallest boundary-preserving change.
2. Edit cron jobs.json or add a second scheduler. Rejected: violates the cron ownership boundary and duplicates scheduling state.
3. Make cron call dispatcher internals directly. Rejected: would let cron claim/spawn and bypass the dispatcher lease gate.
4. Create a new repository. Rejected by parent triage; Hermes fork is the approved source.
