"""Fail-closed metadata-only lateral agent-bus contract."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True)
class LateralMessage:
    message_id: str
    source_agent_id: str
    target_agent_id: str
    user_id: str
    installation_id: str
    login_surface_id: str
    source_ref: str
    recorded_at: float
    freshness_ttl: float
    classification: str
    metadata: dict[str, str]

    def status(self, *, now: float | None = None) -> str:
        age = (now or time.time()) - self.recorded_at
        return "FRESH" if age <= self.freshness_ttl else "STALE"

    def as_dict(self):
        return asdict(self) | {"freshness": self.status()}


def make_message(*, message_id: str, source_agent_id: str, target_agent_id: str, user_id: str, installation_id: str, login_surface_id: str, source_ref: str, classification: str, metadata: dict[str, str], recorded_at: float | None = None, freshness_ttl: float = 900) -> LateralMessage:
    if not all(str(x).strip() for x in (message_id, source_agent_id, target_agent_id, user_id, installation_id, login_surface_id, source_ref)):
        raise ValueError("lateral message requires scoped identity and provenance")
    if any(any(word in key.lower() for word in ("raw", "payload", "content", "secret", "token", "password")) for key in metadata):
        raise ValueError("lateral metadata contains forbidden/private field")
    return LateralMessage(message_id, source_agent_id, target_agent_id, user_id, installation_id, login_surface_id, source_ref, recorded_at or time.time(), freshness_ttl, classification, dict(metadata))


def append_message(path: str | Path, message: LateralMessage) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def read_messages(path: str | Path, *, target_agent_id: str, user_id: str, installation_id: str, login_surface_id: str, now: float | None = None) -> tuple[LateralMessage, ...]:
    target = Path(path)
    if not target.is_file():
        return ()
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        data = json.loads(line)
        if (data.get("target_agent_id"), data.get("user_id"), data.get("installation_id"), data.get("login_surface_id")) != (target_agent_id, user_id, installation_id, login_surface_id):
            continue
        msg = LateralMessage(**{key: data[key] for key in LateralMessage.__dataclass_fields__})
        if msg.status(now=now) == "FRESH": out.append(msg)
    return tuple(out)
