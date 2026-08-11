"""Read-only per-user topology bootstrap for Opus/Hermes startup.

The scanner produces a metadata-only snapshot so Opus can route a turn using
fresh principal/domain/steward/memory/runtime context instead of guessing. It
never writes to Neo4j, Qdrant, Life Contracts, agents, connectors or consent.

Usage:
    python -m tools.mwp_user_topology_startup --user morten --once

The user must be explicit via ``--user`` or ``HERMES_USER_ID``. A missing user
is a BLOCK, never a silent fallback to a shared/default principal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


DEFAULT_LIFE_CONTRACT_API = "http://192.168.40.12:8010/life-contract/facts"
DEFAULT_STEWARD_CONTEXT_API = "http://192.168.40.12:8010/life-contract/steward-context"
DEFAULT_MEMORY_API = "http://192.168.40.12:8010/api/v1/memory/layers"
DEFAULT_HOSTS = {
    "dot12": "192.168.40.12",
    "dot13": "192.168.40.13",
    "dot14": "192.168.40.14",
    "dot15": "192.168.40.15",
}


@dataclass(frozen=True)
class Probe:
    status: str
    detail: str = ""
    http_status: int | None = None
    age_seconds: float | None = None


@dataclass(frozen=True)
class UserTopologySnapshot:
    recorded_at: str
    installation_id: str
    login_surface_id: str
    principal: str
    status: str
    reason: str
    life_contract: Probe
    domains: Mapping[str, Mapping[str, Any]]
    memory: Probe
    runtime_hosts: Mapping[str, Probe]
    source: str = "mwp_user_topology_startup"
    schema_version: str = "mwp-user-topology-v1"
    topology: Mapping[str, Any] = field(default_factory=dict)
    llm: Mapping[str, Any] = field(default_factory=dict)
    device: Mapping[str, Any] = field(default_factory=dict)
    transport: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_ref(value: str, *, prefix: str) -> str:
    """Return a non-secret stable reference for an identity input."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def llm_identity(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Project the active model route without exposing credentials.

    The scanner cannot infer a model identity from a provider label alone. The
    runtime must stamp these values explicitly; absent values remain
    ``UNVERIFIED`` rather than falling back to a guessed model.
    """
    source = env if env is not None else os.environ
    provider = str(source.get("HERMES_MODEL_PROVIDER", "")).strip()
    model = str(source.get("HERMES_MODEL_ID", "")).strip()
    route = str(source.get("HERMES_MODEL_ROUTE", "")).strip()
    api_mode = str(source.get("HERMES_MODEL_API_MODE", "")).strip()
    instance = str(source.get("HERMES_MODEL_INSTANCE_ID", "")).strip()
    complete = bool(provider and model)
    return {
        "status": "LIVE" if complete else "UNVERIFIED",
        "provider": provider or None,
        "model": model or None,
        "route": route or None,
        "api_mode": api_mode or None,
        "instance_id": instance or None,
        "source": "runtime-stamped" if complete else "missing-runtime-stamp",
    }


def device_identity(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Project device identity as a scoped, non-credential metadata envelope."""
    source = env if env is not None else os.environ
    explicit = str(source.get("HERMES_DEVICE_ID", "")).strip()
    seed = explicit or str(source.get("HOSTNAME", "")).strip()
    device_id = _stable_ref(seed, prefix="device") if seed else None
    device_class = str(source.get("HERMES_DEVICE_CLASS", "")).strip().lower()
    if not device_class:
        device_class = "desktop" if source.get("DISPLAY") or source.get("WAYLAND_DISPLAY") else "unknown"
    return {
        "status": "LIVE" if device_id and device_class != "unknown" else "UNVERIFIED",
        "device_id": device_id,
        "device_class": device_class,
        "source": "explicit-or-host-scoped",
    }


def transport_identity(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Describe local/SSH transport without persisting raw hop credentials."""
    source = env if env is not None else os.environ
    declared = str(source.get("HERMES_TRANSPORT", "")).strip().lower()
    ssh_connection = str(source.get("SSH_CONNECTION", "")).strip()
    transport = declared or ("ssh" if ssh_connection else "local")
    hop_seed = str(source.get("HERMES_SSH_SESSION_ID", "")).strip() or ssh_connection
    return {
        "status": "LIVE" if transport in {"local", "ssh", "gateway", "desktop"} else "UNVERIFIED",
        "transport": transport,
        "ssh_hop_ref": _stable_ref(hop_seed, prefix="ssh-hop") if hop_seed else None,
        "gateway_surface": str(source.get("HERMES_GATEWAY_SURFACE", "")).strip() or None,
        "source": "runtime-or-ssh-environment",
    }


def _user(explicit: str | None) -> str:
    value = (explicit or os.environ.get("HERMES_USER_ID") or "").strip().lower()
    if not value or value in {"default", "anonymous", "system", "morpheus"}:
        raise ValueError("explicit canonical HERMES_USER_ID/--user is required")
    return value


def _get_json(url: str, *, timeout: float = 10.0) -> tuple[Probe, Mapping[str, Any]]:
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
            return Probe("LIVE", http_status=response.status), body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as exc:
        return Probe("BLOCKED", f"HTTP {exc.code}", http_status=exc.code), {}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return Probe("UNREACHABLE", type(exc).__name__), {}


def _probe_contract(user: str, *, api: str) -> tuple[Probe, Mapping[str, Any]]:
    url = api.rstrip("/") + "?" + urllib.parse.urlencode({"user_id": user})
    return _get_json(url)


def _probe_domains(user: str, contract: Mapping[str, Any], *, api: str) -> dict[str, Mapping[str, Any]]:
    domains = contract.get("domains")
    if not isinstance(domains, dict):
        return {}
    output: dict[str, Mapping[str, Any]] = {}
    for domain in sorted(str(key).upper() for key in domains):
        query = urllib.parse.urlencode({"domain": domain, "user_id": user})
        probe, body = _get_json(api.rstrip("/") + "?" + query)
        output[domain] = {
            "status": probe.status,
            "steward_id": body.get("steward_id"),
            "resolved": bool(body.get("resolved")),
            "memory_scope": body.get("memory_scope"),
            "contract_version": body.get("contract_version"),
            "http_status": probe.http_status,
        }
    return output


def _probe_memory(user: str, *, api: str) -> Probe:
    query = urllib.parse.urlencode({"user": user})
    probe, body = _get_json(api.rstrip("/") + "?" + query, timeout=20.0)
    if probe.status != "LIVE":
        return probe
    layers = body.get("layers")
    if not isinstance(layers, list):
        return Probe("STALE", "memory API returned no layer list", http_status=probe.http_status)
    return Probe("LIVE", f"canonical_layers={len(layers)}", http_status=probe.http_status)


def _probe_hosts(hosts: Mapping[str, str]) -> dict[str, Probe]:
    result: dict[str, Probe] = {}
    for name, host in hosts.items():
        try:
            with socket.create_connection((host, 22), timeout=2):
                result[name] = Probe("LIVE", "ssh-port-reachable")
        except OSError as exc:
            result[name] = Probe("UNREACHABLE", type(exc).__name__)
    return result


def _probe_url(url: str, *, timeout: float = 5.0) -> Probe:
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json, text/plain"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Probe("LIVE", http_status=response.status)
    except urllib.error.HTTPError as exc:
        return Probe("BLOCKED", f"HTTP {exc.code}", http_status=exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return Probe("UNREACHABLE", type(exc).__name__)


def _probe_user_learning(user: str) -> Probe:
    history_probe, history = _get_json(f"http://192.168.40.12:8010/api/v1/learning/history/{urllib.parse.quote(user)}?limit=1")
    trends_probe, trends = _get_json(f"http://192.168.40.12:8010/api/v1/learning/trends/{urllib.parse.quote(user)}")
    if history_probe.status == "LIVE" and trends_probe.status == "LIVE":
        return Probe("LIVE", f"history_events={history.get('event_count', 0)};trend={((trends.get('trends') or {}).get('trend'))}")
    return Probe("UNVERIFIED", "user-scoped learning history/trends unavailable")


def _probe_user_goals(user: str) -> Probe:
    probe, body = _get_json(f"http://192.168.40.12:8010/api/v1/bootstrap?user_id={urllib.parse.quote(user)}&refresh=false")
    if probe.status != "LIVE":
        return probe
    active = (body.get("summary") or {}).get("active_projects") or {}
    if active.get("error"):
        return Probe("BLOCKED", str(active["error"]))
    return Probe("UNVERIFIED", "bootstrap active_projects is not canonical per-user goal read")


def _probe_cognitive_layers() -> Probe:
    probe, body = _get_json("http://192.168.40.12:8010/api/v1/cognitive/layers/status")
    if probe.status != "LIVE":
        return probe
    return Probe("LIVE" if body.get("all_available") else "DEGRADED", f"layers={len(body.get('layers') or {})}")


def _build_system_topology(
    principal: str,
    memory: Probe,
    domains: Mapping[str, Mapping[str, Any]],
    runtime_hosts: Mapping[str, Probe],
    learning: Probe,
    goals: Probe,
    cognitive: Probe,
) -> dict[str, Any]:
    components = {
        "neo4j": {"surface": "dot12:7474/7687", "role": "graph-authority", "status": _probe_url("http://192.168.40.12:7474").status},
        "qdrant": {"surface": "dot12:6333/6334", "role": "vector-memory", "status": _probe_url("http://192.168.40.12:6333/healthz").status},
        "symbiose_api": {"surface": "dot12:8010", "role": "system-readback", "status": _probe_url("http://192.168.40.12:8010/health").status},
    }
    unknowns = ["user_cortex"]
    if learning.status != "LIVE":
        unknowns.append("user_learning_state")
    if goals.status != "LIVE":
        unknowns.append("user_goal_state")
    return {
        "architecture": "symbiose-opus-hermes-agent-system",
        "symbiose": {"role": "whole-system-substrate", "authority_surface": "dot12", "components": components},
        "opus": {"role": "intelligence-layer", "principal": principal, "context_scope": "installation+user", "cortex": "UNVERIFIED", "learning": learning.status, "goals": goals.status},
        "hermes": {"role": "agent-and-execution-layer", "runtime_hosts": {k: v.status for k, v in runtime_hosts.items()}},
        "user": {"principal": principal, "memory": memory.status, "cortex": "UNVERIFIED", "learning": learning.status, "goals": goals.status},
        "cognitive": {"system_capability": cognitive.status, "detail": cognitive.detail},
        "agents": {domain: {"steward_id": row.get("steward_id"), "resolved": row.get("resolved"), "memory_scope": row.get("memory_scope")} for domain, row in domains.items()},
        "unknowns": unknowns,
    }


def snapshot(
    user: str,
    *,
    life_contract_api: str = DEFAULT_LIFE_CONTRACT_API,
    steward_context_api: str = DEFAULT_STEWARD_CONTEXT_API,
    memory_api: str = DEFAULT_MEMORY_API,
    hosts: Mapping[str, str] = DEFAULT_HOSTS,
) -> UserTopologySnapshot:
    principal = _user(user)
    lc_probe, contract = _probe_contract(principal, api=life_contract_api)
    domains = _probe_domains(principal, contract, api=steward_context_api) if lc_probe.status == "LIVE" else {}
    memory = _probe_memory(principal, api=memory_api)
    learning = _probe_user_learning(principal)
    goals = _probe_user_goals(principal)
    cognitive = _probe_cognitive_layers()
    runtime_hosts = _probe_hosts(hosts)
    llm = llm_identity()
    device = device_identity()
    transport = transport_identity()

    unresolved = [domain for domain, row in domains.items() if not row.get("resolved")]
    if lc_probe.status != "LIVE":
        status, reason = "BLOCKED", "Life Contract readback unavailable"
    elif unresolved:
        status, reason = "BLOCKED", "unresolved user-domain steward binding"
    elif memory.status not in {"LIVE", "STALE"}:
        status, reason = "DEGRADED", "memory readback unavailable"
    else:
        status, reason = "LIVE", "per-user topology readback assembled"
    return UserTopologySnapshot(
        recorded_at=_now(),
        installation_id=installation_id(),
        login_surface_id=login_surface_id(),
        principal=principal,
        status=status,
        reason=reason,
        life_contract=lc_probe,
        domains=domains,
        memory=memory,
        runtime_hosts=runtime_hosts,
        topology=_build_system_topology(principal, memory, domains, runtime_hosts, learning, goals, cognitive),
        llm=llm,
        device=device,
        transport=transport,
    )


def installation_id(root: str | Path | None = None) -> str:
    """Stable install identity derived from this Hermes home, overrideable for tests."""
    explicit = os.environ.get("HERMES_INSTALL_ID", "").strip()
    if explicit:
        return explicit
    home = Path(root or os.environ.get("HERMES_HOME", "~/.hermes")).expanduser().resolve()
    return "install-" + hashlib.sha256(str(home).encode("utf-8")).hexdigest()[:16]


def login_surface_id(root: str | Path | None = None) -> str:
    """Stable login-surface identity; explicit override wins."""
    explicit = os.environ.get("HERMES_LOGIN_SURFACE_ID", "").strip()
    if explicit:
        return explicit
    raw = "|".join(
        os.environ.get(key, "").strip()
        for key in ("HERMES_SURFACE", "HERMES_PLATFORM", "HERMES_INTERFACE", "HOSTNAME")
    ).strip("|")
    if not raw:
        raw = "default-surface|" + installation_id(root)
    return "surface-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def snapshot_path(
    user: str,
    root: str | Path | None = None,
    *,
    installation_id_value: str | None = None,
    installation_id: str | None = None,
    login_surface_value: str | None = None,
    login_surface: str | None = None,
) -> Path:
    home = Path(root or os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    install = installation_id_value or installation_id or globals()["installation_id"](home)
    surface = login_surface_value or login_surface or globals()["login_surface_id"](home)
    return home / "mwp" / "user-topology" / install / surface / f"{user}.json"


def write_snapshot(snapshot_value: UserTopologySnapshot, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(snapshot_value.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only per-user Opus topology bootstrap")
    parser.add_argument("--user", default=None, help="canonical user id; otherwise HERMES_USER_ID")
    parser.add_argument("--once", action="store_true", help="run one scan and exit")
    parser.add_argument("--output", default=None, help="metadata-only JSON output path")
    args = parser.parse_args(argv)
    try:
        user = _user(args.user)
        result = snapshot(user)
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2
    target = args.output or snapshot_path(user)
    write_snapshot(result, target)
    print(json.dumps({"status": result.status, "principal": result.principal, "output": str(target), "domains": len(result.domains)}))
    # BLOCKED/DEGRADED are valid readback states: the caller must inspect the
    # snapshot rather than lose the startup context because one binding is open.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
