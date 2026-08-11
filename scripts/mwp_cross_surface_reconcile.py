#!/usr/bin/env python3
"""Metadata-only MWP cross-surface reconciler.

Reads existing manifests/receipts and produces a deterministic status report.
It never writes graph, Obsidian, GitHub or runtime state.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def load(name: str) -> dict[str, Any]:
    path = DOCS / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def git_ref_readback() -> dict[str, str]:
    branch = "mwp/uosh-automation-01"
    try:
        local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        local = "UNKNOWN"
    try:
        remote_line = subprocess.check_output(
            ["git", "ls-remote", "https://github.com/supertedai/AGI.git", f"refs/heads/{branch}"],
            cwd=ROOT, text=True, timeout=20, stderr=subprocess.DEVNULL,
        ).strip()
        remote = remote_line.split()[0] if remote_line else "UNKNOWN"
    except (OSError, subprocess.SubprocessError):
        remote = "UNKNOWN"
    return {"branch": branch, "local_head": local, "remote_head": remote, "match": str(local == remote and local != "UNKNOWN")}


def main() -> int:
    sync = load("mwp-cross-surface-sync-manifest-v1.json")
    preflight = load("mwp-destination-write-preflight-v1.json")
    source = load("mwp-source-inventory-readback-v1.json")
    cad = load("mwp-cad-source-to-runtime-matrix-v1.json")
    adrb = load("mwp-adr-bl-source-matrix-v1.json")
    graph = load("mwp-graph-projection-plan-v1.json")
    child = load("mwp-kanban-child-preflight-v1.json")

    obs = preflight.get("obsidian", {})
    obs_receipt = obs.get("write_receipt", {})
    git_readback = git_ref_readback()
    git_status = (
        "VERIFIED"
        if git_readback["match"] == "True"
        else "REMOTE_READBACK_UNAVAILABLE"
        if git_readback["remote_head"] == "UNKNOWN"
        else "DIVERGED"
    )
    destinations = {
        "git": {
            "status": git_status,
            "evidence": git_readback,
        },
        "obsidian": {
            "status": "VERIFIED" if obs_receipt.get("status") == "PASS" and obs_receipt.get("read_after_write") == "PASS" else "BLOCKED",
            "evidence": obs.get("canonical_target_path"),
        },
        "graph": {
            "status": "BOUNDED_VERIFIED" if graph.get("bounded_verified_projection", {}).get("status") == "COMPLETE" else "BLOCKED",
            "evidence": graph.get("bounded_verified_projection", {}).get("relationship"),
        },
        "runtime": {"status": "PARTIAL", "evidence": "metadata receipts only"},
    }
    source_counts = {
        "cad": cad.get("records", []).__len__(),
        "adr": adrb.get("adr_records", []).__len__(),
        "bl": adrb.get("bl_records", []).__len__(),
    }
    source_state = {
        "cad": cad.get("status", "UNKNOWN"),
        "adr": adrb.get("status", "UNKNOWN"),
        "bl": adrb.get("status", "UNKNOWN"),
    }
    blockers = []
    if destinations["git"]["status"] == "REMOTE_READBACK_UNAVAILABLE":
        blockers.append("Git remote readback unavailable from Linux; verify AGI ref via authenticated Mac surface")
    elif destinations["git"]["status"] == "DIVERGED":
        blockers.append("Git local/remote ref divergence")
    if any(v != "VERIFIED" for v in (destinations["git"]["status"], destinations["obsidian"]["status"])):
        blockers.append("required Git/Obsidian receipt missing")
    blockers.extend(["full CAD→ADR→BL→MWP task mapping pending", "freshness convergence across all destinations pending"])
    blockers.extend(child.get("required_before_child", {}).get("role_provider", {}).get("required", [])[:1])
    report = {
        "artifact_id": "mwp-cross-surface-reconcile-readback-v1",
        "status": "BLOCKED_FULL_SYNC" if blockers else "PARTIAL_BOUNDED_SYNC",
        "mode": "metadata-only-read-only",
        "destinations": destinations,
        "source_counts": source_counts,
        "source_states": source_state,
        "bounded_complete": ["Git scoped package", "Obsidian curated namespace", "one Morten graph relationship"],
        "blockers": blockers,
        "next_action": "Resolve source-to-task ownership and implement freshness/drift scheduling; do not promote full synchronization.",
        "raw_payload_included": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
