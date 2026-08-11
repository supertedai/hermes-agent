"""Scoped metadata-only topology drift history."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agent.mwp_flyby_queue import SurfaceIdentity
from agent.mwp_topology_discovery import TopologyReadback


@dataclass(frozen=True)
class DriftRecord:
    installation_id: str
    login_surface_id: str
    user_id: str
    agent_id: str
    last_seen: str
    inventory_hash: str
    version_config_hash: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    def as_dict(self):
        data = asdict(self)
        for key in ("added", "removed", "changed"):
            data[key] = list(data[key])
        return data


def record_from_readback(identity: SurfaceIdentity, readback: TopologyReadback) -> DriftRecord:
    version_config_hash = readback.inventory_hash
    return DriftRecord(identity.installation_id, identity.login_surface_id, identity.user_id, identity.agent_id, readback.recorded_at, readback.inventory_hash, version_config_hash, readback.added, readback.removed, readback.changed)


def append_drift(root: str | Path, record: DriftRecord) -> Path:
    target = Path(root) / record.installation_id / record.login_surface_id / f"{record.user_id}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def read_drift(root: str | Path, identity: SurfaceIdentity) -> tuple[DriftRecord, ...]:
    target = Path(root) / identity.installation_id / identity.login_surface_id / f"{identity.user_id}.jsonl"
    if not target.is_file():
        return ()
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if all(data.get(k) == getattr(identity, k) for k in ("installation_id", "login_surface_id", "user_id", "agent_id")):
            out.append(DriftRecord(**data))
    return tuple(out)
