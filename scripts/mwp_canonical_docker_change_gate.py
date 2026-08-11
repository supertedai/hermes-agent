#!/usr/bin/env python3
"""Canonical .12 MWP Docker change gate.

Runs on the canonical Docker host. Default mode is read-only audit.
Deploy mode is bounded: it backs up target files, copies only declared files,
validates the /repo bind mount, compiles/imports, optionally restarts one
container, probes health/routes, and emits a JSON receipt with rollback paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def docker_mount(container: str) -> dict:
    p = run(["docker", "inspect", "--format", "{{json .Mounts}}", container])
    mounts = json.loads(p.stdout)
    return next((m for m in mounts if m.get("Destination") == "/repo"), {})


def container_hash(container: str, rel: str) -> str | None:
    p = run(["docker", "exec", container, "sha256sum", f"/repo/{rel}"], check=False)
    if p.returncode:
        return None
    return p.stdout.split()[0]


def probe(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = body[:2000]
            return {"url": url, "http": r.status, "payload": payload}
    except urllib.error.HTTPError as e:
        return {"url": url, "http": e.code, "error": e.read().decode("utf-8", "replace")[:2000]}
    except Exception as e:  # pragma: no cover - host-specific
        return {"url": url, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("audit", "deploy"), default="audit")
    ap.add_argument("--source-root", default="/home/byopus/AGI-staging")
    ap.add_argument("--canonical-root", default="/home/byopus/AGI")
    ap.add_argument("--container", default="efc-unified-api")
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--health-url", default="http://127.0.0.1:8010/health")
    ap.add_argument("--route-url", default="http://127.0.0.1:8010/api/mwp/runtime")
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--receipt", default="")
    args = ap.parse_args()

    source = Path(args.source_root).resolve()
    canonical = Path(args.canonical_root).resolve()
    started = time.strftime("%Y%m%dT%H%M%S%z")
    backup_root = canonical / ".mwp-change-backups" / started
    receipt_path = Path(args.receipt) if args.receipt else canonical / "docs" / "mwp-docker-change-receipts" / f"{started}.json"
    receipt: dict = {
        "artifact_id": "mwp-canonical-docker-change-gate-v1",
        "mode": args.mode,
        "status": "STARTED",
        "host": "canonical-docker-host",
        "source_root": str(source),
        "canonical_root": str(canonical),
        "container": args.container,
        "files": [],
        "mutation": {"copy": False, "restart": False, "rollback": False},
        "probes": [],
        "rollback_root": str(backup_root),
    }

    try:
        mount = docker_mount(args.container)
        receipt["repo_mount"] = mount
        if mount.get("Source") != str(canonical) or mount.get("Destination") != "/repo":
            raise RuntimeError(f"unsafe /repo mount: {mount}")

        for rel in args.files:
            rel_path = Path(rel)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                raise ValueError(f"unsafe relative file: {rel}")
            src = source / rel_path
            dst = canonical / rel_path
            if not src.is_file():
                raise FileNotFoundError(src)
            row = {"path": rel, "source": {}, "canonical_before": {}, "container_before": None}
            row["source"] = {"sha256": sha256(src), "bytes": src.stat().st_size}
            if dst.exists():
                row["canonical_before"] = {"sha256": sha256(dst), "bytes": dst.stat().st_size}
            row["container_before"] = container_hash(args.container, rel)
            receipt["files"].append(row)

        if args.mode == "deploy":
            backup_root.mkdir(parents=True, exist_ok=True)
            for row in receipt["files"]:
                rel = row["path"]
                src, dst = source / rel, canonical / rel
                if dst.exists():
                    backup = backup_root / rel
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    run(["sudo", "cp", "-p", str(dst), str(backup)])
                mode = format(src.stat().st_mode & 0o777, "04o")
                run(["sudo", "install", "-D", "-m", mode, str(src), str(dst)])
            receipt["mutation"]["copy"] = True

        # Validate canonical and bind-mounted /repo content.
        for row in receipt["files"]:
            rel = row["path"]
            dst = canonical / rel
            after = sha256(dst)
            row["canonical_after"] = {"sha256": after, "bytes": dst.stat().st_size}
            row["container_after"] = container_hash(args.container, rel)
            if row["container_after"] != after:
                raise RuntimeError(f"canonical/container hash divergence: {rel}")
            if args.mode == "deploy" and after != row["source"]["sha256"]:
                raise RuntimeError(f"deploy hash convergence failed: {rel}")
            if args.mode == "audit" and after != row["source"]["sha256"]:
                row["source_canonical_drift"] = True

        compile_targets = [r["path"] for r in receipt["files"] if r["path"].endswith(".py")]
        for rel in compile_targets:
            p = run(["docker", "exec", args.container, "python", "-m", "py_compile", f"/repo/{rel}"], check=False)
            if p.returncode:
                raise RuntimeError(f"container compile failed for {rel}: {p.stderr[-2000:]}")
        receipt["container_compile"] = "PASS"

        if args.restart and args.mode == "deploy":
            p = run(["docker", "restart", args.container], check=False)
            if p.returncode:
                raise RuntimeError(f"restart failed: {p.stderr[-2000:]}")
            receipt["mutation"]["restart"] = True
            time.sleep(8)

        receipt["probes"] = [probe(args.health_url), probe(args.route_url)]
        if any("http" not in p or p["http"] >= 500 for p in receipt["probes"]):
            raise RuntimeError("health/route probe failed")
        drift = any(row.get("source_canonical_drift") for row in receipt["files"])
        receipt["status"] = "DRIFT_DETECTED" if args.mode == "audit" and drift else ("AUDIT_PASS" if args.mode == "audit" else "DEPLOY_PASS")
        receipt["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    except Exception as exc:
        receipt["status"] = "FAILED"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        if args.mode == "deploy" and receipt["mutation"]["copy"]:
            receipt["rollback_available"] = True
        receipt["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 1

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
