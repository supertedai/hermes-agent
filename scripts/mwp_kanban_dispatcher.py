#!/usr/bin/env python3
"""Co-located MWP dispatcher for the canonical Hermes Kanban board.

This reuses Hermes' single-writer dispatcher, leases, heartbeats and worker
lifecycle. The only added behavior is the external MWP pre-claim policy.
Default mode is one bounded tick; ``--loop`` is explicit.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

MWP_REPO = Path(__file__).resolve().parents[1]
HERMES_REPO = Path("/home/agent/agent-layer/hermes-agent")
import sys
for path in (MWP_REPO, HERMES_REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent.mwp_kanban_preclaim import preclaim_policy  # noqa: E402
from hermes_cli import kanban_db  # noqa: E402


def run_once(*, max_spawn: int = 1, dry_run: bool = False) -> dict[str, object]:
    with kanban_db.connect() as conn:
        result = kanban_db.dispatch_once(
            conn,
            max_spawn=max_spawn,
            dry_run=dry_run,
            preclaim_fn=preclaim_policy,
        )
    # BL-4003: statusordet skal beskrive UTFALL, ikke at ticken ble kalt.
    # Foer denne endringen rapporterte HVER tick "EXECUTED" med spawned: [] --
    # hvert 60. sekund i doegnevis. Groenn logg, null arbeid. Fra fabricens side
    # er en slik tick like doed som en falsk groenn: ingenting nedstroems kan
    # skille "kjoerte" fra "gjorde".
    #
    # BENIGN_SIGNALS er felt hvis EGEN docstring i kanban_db sier "NOT an
    # operator-actionable failure" -- forventet stabiltilstand paa multi-lane-
    # oppsett. Et foerste forsoek paa denne fiksen talte dem som arbeid, og
    # reproduserte dermed noeyaktig den falske groennfargen den skulle fjerne
    # (maalt: signals=["skipped_nonspawnable"] paa hver eneste tick).
    #
    # "signals" i utdata lister ALLE sanne felt -- ogsaa de benigne -- slik at
    # statusordet kan etterproeves i stedet for aa maatte tros.
    BENIGN_SIGNALS = ("skipped_nonspawnable", "skipped_per_profile_capped")
    import dataclasses as _dc
    signals = sorted(
        f.name for f in _dc.fields(result)
        if f.name != "skipped_locked" and getattr(result, f.name)
    )
    actionable = [x for x in signals if x not in BENIGN_SIGNALS]
    if dry_run:
        status = "DRY_RUN"
    elif result.skipped_locked:
        status = "SKIPPED_LOCKED"
    else:
        status = "EXECUTED" if actionable else "IDLE"

    return {
        "artifact": "mwp-co-located-dispatcher-tick-v1",
        "status": status,
        "max_spawn": max_spawn,
        "spawned": list(result.spawned),
        "preclaim_blocked": list(result.preclaim_blocked),
        "reclaimed": result.reclaimed,
        "stale": list(result.stale),
        "crashed": list(result.crashed),
        "auto_blocked": list(result.auto_blocked),
        "skipped_locked": result.skipped_locked,
        "signals": signals,
        "actionable_signals": actionable,
        "raw_payload_included": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-spawn", type=int, default=1)
    args = parser.parse_args()
    while True:
        print(json.dumps(run_once(max_spawn=args.max_spawn, dry_run=args.dry_run), sort_keys=True), flush=True)
        if not args.loop:
            return 0
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
