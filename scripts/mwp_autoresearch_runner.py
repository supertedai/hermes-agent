"""Governed wrapper for the isolated Karpathy autoresearch checkout.

Dry-run is the only default. Training requires explicit BL-3935, a clean
checkout, an NVIDIA GPU and an explicit allow flag. The wrapper never grants
access to Hermes/MWP authority or production paths.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

DEFAULT_REPO = Path(__file__).resolve().parents[1].parent / "karpathy-autoresearch"


def git_output(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT).strip()


def gpu_available() -> bool:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return False
    return subprocess.run([binary, "-L"], capture_output=True, text=True, timeout=10).returncode == 0


def receipt(repo: Path, *, run: bool, allow_training: bool, bl_ref: str) -> dict[str, object]:
    if not (repo / ".git").is_dir():
        return {"status": "BLOCKED", "reason": "autoresearch repo is missing", "repo": str(repo)}
    dirty = git_output(repo, "status", "--porcelain")
    head = git_output(repo, "rev-parse", "HEAD")
    files_present = all((repo / name).is_file() for name in ("prepare.py", "train.py", "program.md"))
    if not files_present:
        return {"status": "BLOCKED", "reason": "required autoresearch files missing", "head": head}
    if not run:
        return {"status": "DRY_RUN_PASS", "repo": str(repo), "head": head, "dirty": bool(dirty), "training": False, "side_effects": "none"}
    blockers = []
    if bl_ref != "BL-3935":
        blockers.append("training requires bl_ref=BL-3935")
    if not allow_training:
        blockers.append("training requires --allow-training")
    if dirty:
        blockers.append("autoresearch checkout is dirty")
    if not gpu_available():
        blockers.append("NVIDIA GPU unavailable")
    if blockers:
        return {"status": "BLOCKED", "repo": str(repo), "head": head, "blockers": blockers, "training": False, "side_effects": "none"}
    return {"status": "READY_GATED", "repo": str(repo), "head": head, "training": True, "side_effects": "not_started"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--allow-training", action="store_true")
    parser.add_argument("--bl-ref", default="")
    args = parser.parse_args()
    result = receipt(args.repo.expanduser().resolve(), run=args.run, allow_training=args.allow_training, bl_ref=args.bl_ref)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"DRY_RUN_PASS", "READY_GATED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
