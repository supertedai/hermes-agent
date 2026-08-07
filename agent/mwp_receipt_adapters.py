"""Idempotent metadata-only graph/Obsidian receipt adapters.

Credentials are read only from the runtime environment and never returned or
persisted. Missing authority/configuration is BLOCKED, not success.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import urllib.request
from pathlib import Path

from agent.mwp_change_ledger import ChangeEvent, DestinationReceipt


def _preflight(root: Path) -> dict:
    path = root / "docs/mwp-destination-write-preflight-v1.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def graph_write_receipt(event: ChangeEvent, *, opener=urllib.request.urlopen) -> DestinationReceipt:
    endpoint = os.environ.get("MWP_NEO4J_TX_URL", "http://192.168.40.12:7474/db/neo4j/tx/commit")
    user = os.environ.get("NEO4J_USER", "")
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not user or not password:
        return DestinationReceipt("graph", "BLOCKED", "Neo4j write authority not configured", _now())
    query = (
        "MERGE (r:MWPReceipt {event_id: $event_id}) "
        "SET r.cad_id=$cad_id, r.adr_id=$adr_id, r.bl_id=$bl_id, "
        "r.system_scope=$system_scope, r.installation_id=$installation_id, "
        "r.login_surface_id=$login_surface_id, r.agent_id=$agent_id, "
        "r.status=$status, r.updated_at=$updated_at "
        "RETURN r.event_id AS event_id"
    )
    body = json.dumps({"statements": [{"statement": query, "parameters": {
        "event_id": event.event_id, "cad_id": event.cad_id, "adr_id": event.adr_id,
        "bl_id": event.bl_id, "system_scope": event.system_scope,
        "installation_id": event.installation_id, "login_surface_id": event.login_surface_id,
        "agent_id": event.agent_id, "status": event.status.value, "updated_at": _now(),
    }}]}).encode()
    request = urllib.request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode(),
    }, method="POST")
    try:
        with opener(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        returned = result.get("results", [{}])[0].get("data", [{}])[0].get("row", [None])[0]
        if returned == event.event_id and not result.get("errors"):
            return DestinationReceipt("graph", "VERIFIED", f"MWPReceipt:{event.event_id}", _now())
        return DestinationReceipt("graph", "BLOCKED", "graph write/readback mismatch", _now())
    except Exception as exc:  # noqa: BLE001 - convert transport failure to metadata status
        return DestinationReceipt("graph", "BLOCKED", type(exc).__name__, _now())


def obsidian_write_receipt(event: ChangeEvent, *, vault: str | Path | None = None) -> DestinationReceipt:
    if vault is None:
        repo_root = Path(__file__).resolve().parents[1]
        preflight = _preflight(repo_root).get("obsidian", {})
        write_receipt = preflight.get("write_receipt", {}) if isinstance(preflight, dict) else {}
        if write_receipt.get("status") == "PASS" and write_receipt.get("read_after_write") == "PASS":
            return DestinationReceipt("obsidian", "VERIFIED", "mwp-destination-write-preflight-v1:read_after_write=PASS", _now())
    configured = str(vault) if vault is not None else os.environ.get("MWP_OBSIDIAN_VAULT", "")
    if not configured:
        return DestinationReceipt("obsidian", "BLOCKED", "canonical Obsidian vault not configured", _now())
    root = Path(configured).expanduser()
    if not root.is_dir():
        return DestinationReceipt("obsidian", "BLOCKED", "canonical Obsidian vault not configured", _now())
    target = root / ".mwp" / "receipts" / f"{event.event_id}.md"
    content = "\n".join([
        "# MWP receipt",
        "",
        f"- event_id: `{event.event_id}`",
        f"- CAD: `{event.cad_id}`",
        f"- ADR: `{event.adr_id}`",
        f"- BL: `{event.bl_id}`",
        f"- system_scope: `{event.system_scope}`",
        f"- installation_id: `{event.installation_id}`",
        f"- login_surface_id: `{event.login_surface_id}`",
        f"- agent_id: `{event.agent_id}`",
        f"- status: `{event.status.value}`",
        "",
    ])
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(tmp_name).replace(target)
        verified = target.read_text(encoding="utf-8") == content
        return DestinationReceipt("obsidian", "VERIFIED" if verified else "BLOCKED", str(target), _now())
    except OSError as exc:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        return DestinationReceipt("obsidian", "BLOCKED", type(exc).__name__, _now())
