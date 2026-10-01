"""Placement test: which base a dispatcher-created kanban worktree is cut from.

Measured defect (2026-10-01, ``t_53b2673b``): a board's ``default_workdir`` — the
dispatcher's anchor for ``workspace_kind=worktree`` cards — is often parked on
*another* card's branch. For the ``default`` board it stood on
``wt/t_acbeed4d-konsol-alarm``, and ``_ensure_git_worktree`` cut new branches from
the primary tree's literal ``HEAD``, so six branches born since 2026-09-30 16:29
inherited that foreign tip and every card opened a diff carrying a foreign card's
commit.

The anchor must be the *fetched remote tip* (``origin/main``). Local ``HEAD``
stays the base only as a **named** fallback when the fetch cannot reach the
remote. Reusing an existing tree is named too, and a tree checked out on another
branch is refused rather than silently run on.

Red on the pre-fix code: it cuts from ``HEAD`` and returns ``None`` (no label).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_cli import kanban_db_workspace as kbw


def _git(*args: str, cwd: str | Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout


def _commit(repo: Path, message: str) -> str:
    (repo / "file.txt").write_text(f"{message}\n", encoding="utf-8")
    _git("-C", str(repo), "add", "-A")
    _git("-C", str(repo), "commit", "-m", message)
    return _git("-C", str(repo), "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A project repo whose primary tree is parked on another card's branch.

    ``origin/main`` is at ``main-2``; the checked-out branch ``wt/other-card``
    carries one *unpushed* commit on top of it — the measured 2026-10-01 state of
    the ``default`` board's ``default_workdir``.
    """
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(origin))
    project = tmp_path / "project"
    _git("clone", str(origin), str(project))
    _git("-C", str(project), "config", "user.email", "t@example.com")
    _git("-C", str(project), "config", "user.name", "t")
    _commit(project, "main-1")
    _git("-C", str(project), "push", "origin", "HEAD:main")
    _commit(project, "main-2")
    _git("-C", str(project), "push", "origin", "HEAD:main")
    _git("-C", str(project), "switch", "-c", "wt/other-card")
    _commit(project, "foreign card's commit")
    _git("-C", str(project), "fetch", "origin")
    return project


@pytest.fixture
def repo_pushed_foreign(tmp_path: Path) -> Path:
    """The *pushed* live form measured on the ``default`` board 2026-10-01.

    Like ``repo``, but the foreign card's branch is **pushed and tracked**
    (``push -u origin HEAD``): ``@{upstream}`` then resolves to
    ``origin/wt/foreign`` — the foreign branch's own remote tip. That is the
    state the review round 1 reproduction stood on (the primary tree was on
    ``wt/t_acbeed4d-konsol-alarm``, whose upstream is a real remote ref), and
    it is the state a base resolver that prefers ``@{upstream}`` gets wrong.
    """
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(origin))
    project = tmp_path / "project"
    _git("clone", str(origin), str(project))
    _git("-C", str(project), "config", "user.email", "t@example.com")
    _git("-C", str(project), "config", "user.name", "t")
    _commit(project, "main-1")
    _git("-C", str(project), "push", "origin", "HEAD:main")
    _commit(project, "main-2")
    _git("-C", str(project), "push", "origin", "HEAD:main")
    _git("-C", str(project), "switch", "-c", "wt/foreign")
    _commit(project, "foreign card's commit")
    _git("-C", str(project), "push", "-u", "origin", "HEAD:wt/foreign")
    return project


def _new_tree(repo: Path, task_id: str) -> tuple[Path, str]:
    target = repo / ".worktrees" / task_id
    label = kbw._ensure_git_worktree(repo, target, f"wt/{task_id}")
    # ``label`` is None on the pre-fix code (which returns nothing) — keep the
    # assertions readable instead of dying in a TypeError.
    return target, label or ""


# ---------------------------------------------------------------------------
# (a) the remote tip is the anchor — not the primary tree's literal HEAD
# ---------------------------------------------------------------------------


def test_new_worktree_is_cut_from_the_remote_tip_not_the_primary_head(repo: Path) -> None:
    remote_tip = _git("-C", str(repo), "rev-parse", "origin/main").strip()
    foreign_tip = _git("-C", str(repo), "rev-parse", "HEAD").strip()
    assert remote_tip != foreign_tip, "fixture premise: the primary tree stands off the tip"

    target, label = _new_tree(repo, "t_aaaa1111")

    head = _git("-C", str(target), "rev-parse", "HEAD").strip()
    assert head == remote_tip, (
        f"worktree was cut from {head}, expected the fetched remote tip {remote_tip} "
        f"(the primary tree's HEAD is the foreign tip {foreign_tip}); label was {label!r}"
    )
    assert _git("-C", str(target), "rev-list", "--count", "origin/main..HEAD").strip() == "0"
    assert "origin/main" in label, f"the base must be named, got {label!r}"


def test_new_worktree_fetches_a_remote_tip_that_moved_after_the_clone(
    repo: Path, tmp_path: Path
) -> None:
    writer = tmp_path / "writer"
    _git("clone", str(tmp_path / "origin.git"), str(writer))
    _git("-C", str(writer), "config", "user.email", "w@example.com")
    _git("-C", str(writer), "config", "user.name", "w")
    advanced = _commit(writer, "main-3")
    _git("-C", str(writer), "push", "origin", "HEAD:main")
    # Do not let the freshness window hand back the pre-push cached ref.
    (repo / ".git" / "FETCH_HEAD").unlink(missing_ok=True)

    target, label = _new_tree(repo, "t_bbbb2222")

    head = _git("-C", str(target), "rev-parse", "HEAD").strip()
    assert head == advanced, f"expected the refetched tip {advanced}, got {head} ({label!r})"


# ---------------------------------------------------------------------------
# (a2) the *pushed* live form: the primary tree tracks a foreign branch whose
#      upstream resolves — the anchor must still be origin/main, not @{upstream}
# ---------------------------------------------------------------------------


def test_new_worktree_ignores_a_pushed_foreign_upstream(
    repo_pushed_foreign: Path,
) -> None:
    # Premise: the current branch's upstream IS the foreign branch's own remote
    # tip (push -u), and that tip is not origin/main.
    upstream = _git("-C", str(repo_pushed_foreign), "rev-parse", "@{upstream}").strip()
    assert upstream == _git("-C", str(repo_pushed_foreign), "rev-parse", "HEAD").strip(), (
        "fixture premise: the primary tree tracks the pushed foreign branch"
    )
    remote_tip = _git("-C", str(repo_pushed_foreign), "rev-parse", "origin/main").strip()
    assert upstream != remote_tip, "fixture premise: the foreign tip is not the remote tip"

    target, label = _new_tree(repo_pushed_foreign, "t_abcd0001")

    head = _git("-C", str(target), "rev-parse", "HEAD").strip()
    assert head == remote_tip, (
        f"worktree was cut from {head}, expected the remote default branch tip "
        f"{remote_tip}; with the primary tree on a pushed foreign branch, "
        f"@{{upstream}} resolves to the FOREIGN tip {upstream}, and that must not "
        f"become the anchor. label was {label!r}"
    )
    assert (
        _git("-C", str(target), "rev-list", "--count", "origin/main..HEAD").strip() == "0"
    ), "the new tree must not carry any commit beyond origin/main"
    assert "origin/main" in label, f"the base must be named, got {label!r}"


def test_reuse_on_the_same_branch_names_origin_main_despite_a_pushed_foreign_upstream(
    repo_pushed_foreign: Path,
) -> None:
    target, _ = _new_tree(repo_pushed_foreign, "t_abcd0002")
    head = _git("-C", str(target), "rev-parse", "HEAD").strip()

    label = kbw._ensure_git_worktree(repo_pushed_foreign, target, "wt/t_abcd0002") or ""

    assert "wt/t_abcd0002" in label
    assert head[:12] in label, f"the reused tree's HEAD must be named, got {label!r}"
    assert "origin/main" in label, (
        f"the reuse path names the intended base through the same resolver; "
        f"a pushed foreign upstream must not leak into it, got {label!r}"
    )


# ---------------------------------------------------------------------------
# (b) fetch failure -> HEAD as a NAMED fallback
# ---------------------------------------------------------------------------


def test_fetch_failure_falls_back_to_head_and_names_the_fallback(
    repo: Path, tmp_path: Path
) -> None:
    primary_head = _git("-C", str(repo), "rev-parse", "HEAD").strip()
    _git("-C", str(repo), "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    _git("-C", str(repo), "update-ref", "-d", "refs/remotes/origin/main")
    _git("-C", str(repo), "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")

    target, label = _new_tree(repo, "t_cccc3333")

    head = _git("-C", str(target), "rev-parse", "HEAD").strip()
    assert head == primary_head, "with no reachable remote the base is the local HEAD"
    assert label.startswith("HEAD"), f"the fallback must name itself, got {label!r}"
    assert "fetch" in label.lower() or "remote" in label.lower(), (
        f"the named fallback must say why it fell back, got {label!r}"
    )


# ---------------------------------------------------------------------------
# reuse of an existing tree: refused on another branch, named on this one
# ---------------------------------------------------------------------------


def test_reuse_of_a_tree_checked_out_on_another_branch_is_refused(repo: Path) -> None:
    target, _ = _new_tree(repo, "t_dddd4444")
    with pytest.raises(RuntimeError) as excinfo:
        kbw._ensure_git_worktree(repo, target, "wt/t_eeee5555")
    message = str(excinfo.value)
    assert "wt/t_dddd4444" in message and "wt/t_eeee5555" in message, message


def test_reuse_on_the_same_branch_is_allowed_and_names_the_tree(repo: Path) -> None:
    target, _ = _new_tree(repo, "t_ffff6666")
    head = _git("-C", str(target), "rev-parse", "HEAD").strip()

    label = kbw._ensure_git_worktree(repo, target, "wt/t_ffff6666") or ""

    assert "wt/t_ffff6666" in label
    assert head[:12] in label, f"the reused tree's HEAD must be named, got {label!r}"
    assert "origin/main" in label, f"the intended base must be named, got {label!r}"


# ---------------------------------------------------------------------------
# a failed add is swept so the retry is not poisoned
# ---------------------------------------------------------------------------


def test_failed_add_sweeps_the_leftover_before_raising(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    swept: list[tuple] = []
    monkeypatch.setattr(
        kbw, "_cleanup_failed_worktree_add", lambda *args, **kwargs: swept.append(args)
    )
    real_git = kbw._git

    def failing_git(repo_root, *args, **kwargs):
        if args[:1] == ("worktree",) and "add" in args:
            return subprocess.CompletedProcess(["git"], 1, "", "fatal: boom")
        return real_git(repo_root, *args, **kwargs)

    monkeypatch.setattr(kbw, "_git", failing_git)

    with pytest.raises(RuntimeError, match="boom"):
        kbw._ensure_git_worktree(repo, repo / ".worktrees" / "t_gggg7777", "wt/t_gggg7777")

    assert swept, "the leftover of a failed add must be swept before the error propagates"
