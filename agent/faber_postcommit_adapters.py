"""Concrete Hermes-local adapters for the Faber postcommit Definition of Done.

``PostcommitLoop`` has always been able to run the chain
``commit_closer → brain_change_log → selfstate → readback → runtime_smoke →
rollback → tests``. What did not exist was a single real implementation of those
callbacks, so the chain had only ever run against test fixtures. That is the gap
this module closes.

Scope, stated rather than implied
---------------------------------
These adapters are **Hermes-local**. ``selfstate`` writes a Faber state record
under HERMES_HOME; it does NOT write into the Symbiose graph, because that graph
has one write gate on ``.13`` and a second, ungated writer from ``.15`` would
produce exactly the unlinked facts that gate exists to prevent. Likewise
``brain_change_log`` appends to Faber's own change log in this repo, not to
Morten's Obsidian vault on ``.13``. Naming them after the surfaces they actually
touch is the point; an adapter that claimed to have written the vault would be
worse than no adapter.

Every step fails CLOSED. ``DefinitionOfDone`` treats an empty evidence string as
a missing step, so an adapter that cannot do its job returns "" and the gate
refuses the landing — it never returns a plausible sentence about work it did
not do.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent


def faber_home() -> Path:
    override = os.environ.get("HERMES_FABER_HOME")
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "faber"
    except Exception:
        return Path(os.path.expanduser("~/.hermes-gui/faber"))


def _git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd or REPO_ROOT),
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# The seven Definition-of-Done steps
# ---------------------------------------------------------------------------

def commit_closer(sha: str, *, repo: Path | None = None) -> str:
    """Verify the commit actually landed, then record its closure.

    'Landed' means reachable from HEAD — not merely that the object exists. A
    commit that exists but sits on no branch is the case a closure record would
    otherwise quietly bless.
    """
    repo = repo or REPO_ROOT
    code, subject = _git("log", "-1", "--format=%H %s", sha, cwd=repo)
    if code != 0:
        return ""
    code, _ = _git("merge-base", "--is-ancestor", sha, "HEAD", cwd=repo)
    if code != 0:
        return ""
    code, files = _git("show", "--name-only", "--format=", sha, cwd=repo)
    touched = [f for f in files.splitlines() if f.strip()] if code == 0 else []
    record = {
        "recorded_at": _now(),
        "commit": sha,
        "subject": subject.split(" ", 1)[-1] if " " in subject else subject,
        "reachable_from_head": True,
        "files": touched,
    }
    if not _append_jsonl(faber_home() / "commit-closures.jsonl", record):
        return ""
    return f"closure recorded: {sha[:12]} reachable from HEAD, {len(touched)} file(s)"


def brain_change_log(sha: str, *, repo: Path | None = None, path: Path | None = None) -> str:
    """Append to Faber's own change log.

    Named for what it touches. Morten's Obsidian vault lives on .13 and is not
    reachable from here; writing a line that claimed otherwise would be the
    failure this whole gate is meant to catch.
    """
    repo = repo or REPO_ROOT
    target = path or (repo / "docs" / "FABER_CHANGE_LOG.md")
    code, subject = _git("log", "-1", "--format=%s", sha, cwd=repo)
    if code != 0:
        return ""
    entry = f"- {_now()} · `{sha[:12]}` — {subject}\n"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(
                "# Faber change log\n\n"
                "Hermes-lokal endringslogg for Faber-landede commits. Dette er IKKE\n"
                "Mortens Obsidian-vault på `.13` — den er en separat, kuratert flate.\n\n",
                encoding="utf-8",
            )
        with target.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except OSError:
        return ""
    return f"change log appended: {target.name} <- {sha[:12]}"


def selfstate(sha: str, *, repo: Path | None = None) -> str:
    """Record Faber's own durable state for this commit — Hermes-local only."""
    repo = repo or REPO_ROOT
    code, meta = _git("log", "-1", "--format=%H%n%an%n%cI%n%s", sha, cwd=repo)
    if code != 0:
        return ""
    parts = meta.splitlines()
    if len(parts) < 4:
        return ""
    record = {
        "recorded_at": _now(),
        "kind": "faber_landing",
        "commit": parts[0],
        "author": parts[1],
        "committed_at": parts[2],
        "subject": parts[3],
        "scope": "hermes.local",
        "note": "Hermes-local Faber state. Not written to the Symbiose graph — "
                "that graph has one write gate on .13 and a second writer here "
                "would create unlinked facts.",
    }
    if not _append_jsonl(faber_home() / "selfstate.jsonl", record):
        return ""
    return f"selfstate recorded (hermes.local): {sha[:12]}"


def readback(sha: str) -> str:
    """Re-read what the previous steps wrote. Claims nothing it cannot find."""
    found = []
    for name, filename in (("closure", "commit-closures.jsonl"), ("selfstate", "selfstate.jsonl")):
        path = faber_home() / filename
        try:
            hit = any(sha in line for line in path.read_text(encoding="utf-8").splitlines())
        except OSError:
            hit = False
        if hit:
            found.append(name)
    log = REPO_ROOT / "docs" / "FABER_CHANGE_LOG.md"
    try:
        if sha[:12] in log.read_text(encoding="utf-8"):
            found.append("change_log")
    except OSError:
        pass
    if len(found) < 3:
        return ""
    return "readback confirms: " + ", ".join(found)


def runtime_smoke(sha: str, *, modules: Sequence[str] = (), repo: Path | None = None) -> str:
    """Import the modules this commit touched, in a fresh interpreter.

    A commit whose own modules cannot be imported has not landed in any sense
    that matters, however green the diff looked.
    """
    repo = repo or REPO_ROOT
    if not modules:
        code, files = _git("show", "--name-only", "--format=", sha, cwd=repo)
        if code != 0:
            return ""
        modules = [
            f[:-3].replace("/", ".")
            for f in files.splitlines()
            if f.endswith(".py") and not f.startswith("tests/")
        ]
    if not modules:
        return f"no importable module in {sha[:12]} — smoke not applicable"
    script = "import importlib\n" + "\n".join(
        f"importlib.import_module({m!r})" for m in modules
    )
    proc = subprocess.run(
        [os.environ.get("HERMES_PYTHON", ".venv/bin/python"), "-c", script],
        cwd=str(repo), capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        return ""
    return f"runtime smoke ok: imported {len(modules)} module(s)"


def rollback(sha: str, *, repo: Path | None = None) -> str:
    """Prove the commit is reversible without touching the worktree."""
    repo = repo or REPO_ROOT
    show = subprocess.run(["git", "show", sha], cwd=str(repo),
                          capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)
    if show.returncode != 0:
        return ""
    check = subprocess.run(["git", "apply", "--reverse", "--check", "-"],
                           cwd=str(repo), input=show.stdout,
                           capture_output=True, text=True, timeout=120)
    if check.returncode != 0:
        return ""
    return f"rollback verified: git revert {sha[:12]} applies cleanly"


def run_tests(paths: Sequence[str], *, repo: Path | None = None) -> str:
    repo = repo or REPO_ROOT
    if not paths:
        return ""
    proc = subprocess.run(
        [os.environ.get("HERMES_PYTHON", ".venv/bin/python"), "-m", "pytest", "-q", *paths],
        cwd=str(repo), capture_output=True, text=True, timeout=900,
    )
    tail = (proc.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else ""
    if proc.returncode != 0 or "passed" not in summary:
        return ""
    return f"tests: {summary}"


# ---------------------------------------------------------------------------
# C2 — learning measurement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LearningEvent:
    commit: str
    goal_id: str
    metric: str
    baseline: float
    after: float
    confidence: float
    status: str
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {"recorded_at": _now(), **asdict(self), "delta": self.after - self.baseline}


def record_learning(
    *,
    commit: str,
    goal_id: str,
    metric: str,
    baseline: float,
    after: float,
    method: str,
    confidence: float,
    log: Path | None = None,
) -> LearningEvent | None:
    """Persist one before/after measurement bound to a commit and a goal.

    This module refuses to *produce* the measurement. It enforces the shape —
    a named metric, both readings, how they were taken, a confidence, and a
    verdict derived from the numbers rather than asserted alongside them. A
    learning event whose baseline and after are identical is `inconclusive`,
    never `confirmed`; that is the case where a claim of learning is easiest
    to make and hardest to justify.
    """
    if not commit.strip() or not goal_id.strip() or not metric.strip() or not method.strip():
        return None
    if not 0.0 <= confidence <= 1.0:
        return None
    if after > baseline:
        status = "confirmed"
    elif after < baseline:
        status = "refuted"
    else:
        status = "inconclusive"
    event = LearningEvent(commit.strip(), goal_id.strip(), metric.strip(),
                          float(baseline), float(after), float(confidence), status, method.strip())
    target = log or (faber_home() / "learning-events.jsonl")
    if not _append_jsonl(target, event.to_dict()):
        return None
    return event
