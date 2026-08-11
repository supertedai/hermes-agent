#!/usr/bin/env python3
"""Metadata-only restore preflight; never restores or mutates data services."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import stat
from pathlib import Path
from typing import Any

SAMPLE_LIMIT = 64 * 1024 * 1024


def sha256(path: Path, limit: int = SAMPLE_LIMIT) -> tuple[str | None, str]:
    if path.stat().st_size > limit:
        return None, "NOT_COMPUTED_OVER_LIMIT"
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest(), "FULL_FILE"


def inspect(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "MISSING"}
    st = path.stat()
    digest, digest_status = sha256(path) if path.is_file() else (None, "DIRECTORY")
    return {
        "path": str(path),
        "exists": True,
        "kind": "file" if stat.S_ISREG(st.st_mode) else "directory",
        "bytes": st.st_size if path.is_file() else None,
        "mtime": st.st_mtime,
        "sha256": digest,
        "sha256_status": digest_status,
        "mime_guess": mimetypes.guess_type(str(path))[0],
        "status": "PHYSICAL_ARTIFACT_FOUND",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-snapshot", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--qdrant-root", type=Path, required=True)
    ap.add_argument("--gnn-root", type=Path, required=True)
    args = ap.parse_args()

    qdrant = sorted(args.qdrant_root.glob("*.snapshot")) if args.qdrant_root.is_dir() else []
    gnn = sorted(p for p in args.gnn_root.rglob("*") if p.suffix in {".pt", ".pth", ".ckpt", ".safetensors"}) if args.gnn_root.is_dir() else []
    report = {
        "artifact_id": "mwp-restore-preflight-readback-v1",
        "status": "PREFLIGHT_ONLY_RESTORE_NOT_ATTEMPTED",
        "mutation": {"restore": False, "delete": False, "service_restart": False, "writes": False},
        "full_snapshot": inspect(args.full_snapshot),
        "archive": inspect(args.archive),
        "qdrant": {"root": str(args.qdrant_root), "count": len(qdrant), "samples": [inspect(p) for p in qdrant[:10]]},
        "gnn": {"root": str(args.gnn_root), "count": len(gnn), "samples": [inspect(p) for p in gnn[:10]]},
        "promotion": "BLOCKED_UNTIL_MANIFEST_DESTINATION_RESTORE_ROLLBACK_EVIDENCE",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
