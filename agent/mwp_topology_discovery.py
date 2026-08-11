"""Metadata-only local topology discovery and drift diff for MWP."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class TopologyItem:
    source: str
    key: str
    status: str
    detail: str

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TopologyReadback:
    recorded_at: str
    inventory_hash: str
    items: tuple[TopologyItem, ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    def as_dict(self):
        return {
            "recorded_at": self.recorded_at,
            "inventory_hash": self.inventory_hash,
            "item_count": len(self.items),
            "items": [item.as_dict() for item in self.items],
            "drift": {"added": list(self.added), "removed": list(self.removed), "changed": list(self.changed)},
        }


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run(command: list[str], runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    try:
        result = runner(command, text=True, capture_output=True, timeout=8, check=False)
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _items_from_lines(source: str, output: str) -> list[TopologyItem]:
    items = []
    for line in output.splitlines():
        value = line.strip()
        if not value:
            continue
        parts = value.split("\t", 1)
        key = parts[0].strip()
        detail = parts[1].strip() if len(parts) > 1 else "present"
        items.append(TopologyItem(source, key, "LIVE", detail[:300]))
    return items


def discover_local(runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> tuple[TopologyItem, ...]:
    """Discover local runtime metadata; never returns command payloads wholesale."""
    items: list[TopologyItem] = []
    items.extend(_items_from_lines("docker", _run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"], runner)))
    items.extend(_items_from_lines("systemd", _run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend"], runner)))
    items.extend(_items_from_lines("listeners", _run(["ss", "-ltnH"], runner)))
    process_output = _run(["ps", "-eo", "pid=,comm=,args="], runner)
    for line in process_output.splitlines():
        fields = line.strip().split(None, 2) if line.strip() else []
        if fields and fields[0].isdigit() and int(fields[0]) == os.getpid():
            continue
        if len(fields) >= 3 and fields[0].isdigit():
            name, command_line = fields[1], fields[2]
        else:
            name = fields[0] if fields else ""
            command_line = line
        if name and name not in {"bwrap", "timeout", "sleep"} and any(term in command_line.lower() for term in ("hermes", "opus", "qdrant", "neo4j", "gnn", "daemon", "uvicorn", "tui")):
            items.append(TopologyItem("process", name, "LIVE", "matched topology process"))
    return tuple(sorted({(item.source, item.key): item for item in items}.values(), key=lambda item: (item.source, item.key)))


def readback(items: Iterable[TopologyItem], previous: TopologyReadback | None = None) -> TopologyReadback:
    ordered = tuple(sorted(items, key=lambda item: (item.source, item.key)))
    canonical = [f"{item.source}|{item.key}|{item.status}|{item.detail}" for item in ordered]
    digest = hashlib.sha256("\n".join(canonical).encode()).hexdigest()
    current = {f"{item.source}:{item.key}": item for item in ordered}
    old = {f"{item.source}:{item.key}": item for item in (previous.items if previous else ())}
    added = tuple(sorted(set(current) - set(old)))
    removed = tuple(sorted(set(old) - set(current)))
    changed = tuple(sorted(k for k in set(current) & set(old) if current[k] != old[k]))
    return TopologyReadback(_timestamp(), digest, ordered, added, removed, changed)


def write_readback(readback_value: TopologyReadback, path: str | Path) -> Path:
    target = Path(path).expanduser(); target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(readback_value.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)
    return target
