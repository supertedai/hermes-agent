"""One-event destination receipt pipeline."""
from __future__ import annotations

from pathlib import Path

from agent.mwp_change_ledger import ChangeEvent, append_event, update_receipts
from agent.mwp_receipt_adapters import graph_write_receipt, obsidian_write_receipt
from agent.mwp_receipt_coordinator import git_receipt


def reconcile_event(event: ChangeEvent, *, repo: str | Path, ledger_path: str | Path, graph_opener=None, vault: str | Path | None = None) -> ChangeEvent:
    """Collect receipts and append the reconciled event with the same identity."""
    git = git_receipt(repo)
    graph = graph_write_receipt(event, opener=graph_opener) if graph_opener is not None else graph_write_receipt(event)
    obsidian = obsidian_write_receipt(event, vault=vault)
    reconciled = update_receipts(event, (git, graph, obsidian))
    append_event(reconciled, ledger_path)
    return reconciled
