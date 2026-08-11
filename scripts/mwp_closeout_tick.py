#!/usr/bin/env python3
"""Refresh the metadata-only MWP final closeout projection."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.mwp_asi_alignment_registry import build_status_quo, refresh_from_topology
from agent.mwp_asi_closeout import evaluate_closeout
from agent.mwp_change_ledger import append_event, record_change
from agent.mwp_receipt_adapters import graph_write_receipt, obsidian_write_receipt
from agent.mwp_receipt_coordinator import git_receipt
from agent.mwp_topology_context import load_topology_context

ROOT = Path(__file__).resolve().parents[1]
SCOPE = {"user_id": "morten", "installation_id": "mwp-status-quo", "login_surface_id": "current-hermes-chat", "agent_id": "opus"}

def main() -> None:
    topology = load_topology_context(ROOT / "docs/mwp-local-topology-readback.json", ttl_seconds=900, scope=SCOPE)
    registry = refresh_from_topology(build_status_quo(), topology)
    event = record_change(action="closeout projection tick", intent="metadata-only receipt status probe", principal="morten", installation_id=SCOPE["installation_id"], login_surface_id=SCOPE["login_surface_id"], agent_id=SCOPE["agent_id"], system_scope="mwp-closeout")
    append_event(event, ROOT / "docs/mwp-autonomous-change-ledger.jsonl")
    receipts = (git_receipt(ROOT), graph_write_receipt(event), obsidian_write_receipt(event))
    closeout = evaluate_closeout(registry, tuple(r.status for r in receipts))
    data = {"scope": SCOPE, "registry": registry.as_dict(), "receipts": [{"destination": r.destination, "status": r.status, "ref": r.ref} for r in receipts], "closeout": {"status": closeout.status, "continue_loop": closeout.continue_loop, "blocker_count": len(closeout.blockers), "blockers": list(closeout.blockers)}}
    target = ROOT / "docs/mwp-final-closeout-readback.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": closeout.status, "registry_open_rows": registry.open_rows, "receipt_statuses": [r.status for r in receipts], "blocker_count": len(closeout.blockers)}))

if __name__ == "__main__":
    main()
