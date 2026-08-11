"""Metadata-only destination receipt coordinator for MWP change events.

Git can be verified locally. Neo4j and Obsidian are never claimed written by a
probe; they require explicit adapter receipts with a stable reference.
"""
from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from agent.mwp_change_ledger import ChangeEvent, DestinationReceipt


def git_receipt(repo: str | Path) -> DestinationReceipt:
    root = str(Path(repo).resolve())
    try:
        commit = subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True, timeout=10).strip()
        status = subprocess.run(["git", "-C", root, "status", "--porcelain"], text=True, capture_output=True, timeout=10)
        if status.returncode != 0:
            return DestinationReceipt("git", "UNVERIFIED", "", "")
        # This is a repository readback, not proof that the event was committed.
        ref = f"repo={root};head={commit};dirty={'yes' if status.stdout else 'no'}"
        return DestinationReceipt("git", "VERIFIED", ref, "runtime-readback")
    except (OSError, subprocess.SubprocessError):
        return DestinationReceipt("git", "UNVERIFIED", "", "")


def graph_probe(url: str | None = None) -> DestinationReceipt:
    endpoint = url or os.environ.get("MWP_GRAPH_HEALTH_URL", "http://192.168.40.12:7474")
    try:
        with urllib.request.urlopen(endpoint, timeout=5) as response:
            # Health/reachability is not a graph-write receipt.
            return DestinationReceipt("graph", "PRESENT_NOT_WRITE_VERIFIED", f"health={response.status};url={endpoint}", "runtime-readback")
    except Exception as exc:  # noqa: BLE001 - metadata-only probe
        return DestinationReceipt("graph", "UNVERIFIED", type(exc).__name__, "runtime-readback")


def obsidian_probe(vault: str | Path | None = None) -> DestinationReceipt:
    configured = str(vault) if vault is not None else os.environ.get("MWP_OBSIDIAN_VAULT", "")
    if not configured.strip():
        return DestinationReceipt("obsidian", "UNVERIFIED", "vault path not configured", "runtime-readback")
    path = Path(configured).expanduser()
    if path.exists() and path.is_dir():
        return DestinationReceipt("obsidian", "PRESENT_NOT_WRITE_VERIFIED", f"vault={path}", "runtime-readback")
    return DestinationReceipt("obsidian", "UNVERIFIED", f"vault missing={path}", "runtime-readback")


def receipts_for_event(event: ChangeEvent, *, repo: str | Path) -> tuple[DestinationReceipt, ...]:
    """Return conservative receipts; never upgrades graph/Obsidian to VERIFIED."""
    return (git_receipt(repo), graph_probe(), obsidian_probe())
