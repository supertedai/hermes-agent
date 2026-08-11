"""Fail-closed installation/login-surface scoped topology snapshot store."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.mwp_flyby_queue import SurfaceIdentity, surface_snapshot_path


def write_scoped_snapshot(root: str | Path, identity: SurfaceIdentity, snapshot: dict[str, Any]) -> Path:
    """Write metadata-only snapshot under the complete installation/surface/user scope."""
    forbidden = {"raw", "payload", "content", "secret", "token", "password", "credential"}
    if any(any(word in str(key).lower() for word in forbidden) for key in snapshot):
        raise ValueError("raw/private snapshot fields are forbidden")
    target = surface_snapshot_path(root, identity)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = dict(snapshot)
    data.update({
        "installation_id": identity.installation_id,
        "login_surface_id": identity.login_surface_id,
        "user_id": identity.user_id,
        "agent_id": identity.agent_id,
    })
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    return target


def read_scoped_snapshot(root: str | Path, identity: SurfaceIdentity) -> dict[str, Any] | None:
    target = surface_snapshot_path(root, identity)
    if not target.is_file():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    expected = {
        "installation_id": identity.installation_id,
        "login_surface_id": identity.login_surface_id,
        "user_id": identity.user_id,
        "agent_id": identity.agent_id,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        return None
    return data
