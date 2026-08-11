#!/usr/bin/env python3
"""Run one metadata-only MWP topology heartbeat tick."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.mwp_change_ledger import append_event, record_change
from agent.mwp_topology_discovery import TopologyItem, TopologyReadback, discover_local, readback, write_readback

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/mwp-local-topology-readback.json"
LEDGER = ROOT / "docs/mwp-autonomous-change-ledger.jsonl"


def _previous() -> TopologyReadback | None:
    if not SNAPSHOT.exists():
        return None
    try:
        data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        items = tuple(TopologyItem(**item) for item in data.get("items", []))
        drift = data.get("drift", {})
        return TopologyReadback(
            recorded_at=str(data.get("recorded_at", "")),
            inventory_hash=str(data.get("inventory_hash", "")),
            items=items,
            added=tuple(drift.get("added", [])),
            removed=tuple(drift.get("removed", [])),
            changed=tuple(drift.get("changed", [])),
        )
    except (OSError, ValueError, TypeError, KeyError):
        return None


def run_tick() -> dict[str, object]:
    previous = _previous()
    current = readback(discover_local(), previous)
    write_readback(current, SNAPSHOT)
    event = record_change(
        action="topology heartbeat tick",
        intent="refresh local topology and persist drift metadata",
        principal="morten",
        installation_id="mwp-status-quo",
        login_surface_id="current-hermes-chat",
        agent_id="opus",
        system_scope="mwp-topology",
        evidence_refs=(str(SNAPSHOT.relative_to(ROOT)), f"inventory_hash:{current.inventory_hash}"),
    )
    append_event(event, LEDGER)
    return {
        "snapshot": str(SNAPSHOT),
        "inventory_hash": current.inventory_hash,
        "item_count": len(current.items),
        "added": current.added,
        "removed": current.removed,
        "changed": current.changed,
        "event_id": event.event_id,
        "status": event.status.value,
        "gap": event.gap,
    }


if __name__ == "__main__":
    print(json.dumps(run_tick(), ensure_ascii=False))
