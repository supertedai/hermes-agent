"""Metadata-only flyby queue and installation-surface isolation helpers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SurfaceIdentity:
    installation_id: str
    login_surface_id: str
    user_id: str
    agent_id: str

    def key(self) -> str:
        return "/".join((self.installation_id, self.login_surface_id, self.user_id, self.agent_id))


@dataclass(frozen=True)
class FlybyDigest:
    flyby_id: str
    classification: str
    claim: str
    evidence: tuple[str, ...]
    impact_on_primary: str
    recommended_action: str
    confidence: str
    target_scope: str
    queued: bool = True

    def as_dict(self):
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


def surface_snapshot_path(root: str | Path, identity: SurfaceIdentity) -> Path:
    return Path(root) / identity.installation_id / identity.login_surface_id / f"{identity.user_id}.json"


def digest_flyby(*, classification: str, claim: str, evidence: Iterable[str], impact_on_primary: str, recommended_action: str, confidence: str, target_scope: str) -> FlybyDigest:
    token = hashlib.sha256("|".join((classification, claim, target_scope, *evidence)).encode()).hexdigest()[:12]
    return FlybyDigest("FLYBY-" + token, classification, claim, tuple(evidence), impact_on_primary, recommended_action, confidence, target_scope)


def enqueue(digest: FlybyDigest, path: str | Path) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(digest.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def route_flyby(
    record: dict[str, object],
    *,
    bounded_worker,
    queue_path: str | Path,
) -> FlybyDigest:
    """Run one bounded metadata worker, distill its result, and queue it."""
    result = bounded_worker({key: record[key] for key in ("id", "source", "scope", "claim") if key in record})
    if not isinstance(result, dict):
        raise ValueError("bounded worker must return metadata mapping")
    forbidden = {"raw", "payload", "content", "secret", "token", "password"}
    if any(any(word in str(key).lower() for word in forbidden) for key in result):
        raise ValueError("worker returned forbidden/private payload field")
    digest = digest_flyby(
        classification=str(result.get("classification", "UNVERIFIED")),
        claim=str(result.get("claim", record.get("claim", ""))),
        evidence=tuple(str(x) for x in result.get("evidence", ())),
        impact_on_primary=str(result.get("impact_on_primary", "unknown")),
        recommended_action=str(result.get("recommended_action", "inspect at safe point")),
        confidence=str(result.get("confidence", "low")),
        target_scope=str(result.get("target_scope", record.get("scope", "unknown"))),
    )
    enqueue(digest, queue_path)
    return digest


def drain_at_safe_point(path: str | Path, *, safe_point: str) -> tuple[FlybyDigest, ...]:
    target = Path(path)
    if not target.exists():
        return ()
    result = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        result.append(FlybyDigest(
            flyby_id=data["flyby_id"], classification=data["classification"], claim=data["claim"],
            evidence=tuple(data.get("evidence", ())), impact_on_primary=data["impact_on_primary"],
            recommended_action=f"safe_point={safe_point}; {data['recommended_action']}",
            confidence=data["confidence"], target_scope=data["target_scope"], queued=False,
        ))
    return tuple(result)
