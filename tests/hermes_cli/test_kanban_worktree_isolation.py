"""Per-task worktree isolation for decompose siblings.

Decompose children used to inherit the root's literal ``workspace_path``,
so every sibling of a worktree-kind root pointed at the SAME checkout —
and ``_resolve_worktree_workspace``'s existing-checkout shortcut reused it
on whatever branch was there, letting sibling workers run concurrently in
one directory on one branch (cross-task provenance corruption, no lock).

Two-part fix under test:
- ``decompose_triage_task`` leaves worktree children's ``workspace_path``
  unset so each child materializes its own ``<repo>/.worktrees/<child-id>``.
- ``_resolve_worktree_workspace`` falls back to a fresh per-task worktree
  when the requested path is occupied by another task's branch (heals
  pre-existing rows that still carry a shared path).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    """Isolated HERMES_HOME with an empty kanban DB."""
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git", "-C", str(cwd),
            "-c", "user.name=Test User",
            "-c", "user.email=test@example.com",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        check=True, capture_output=True, text=True,
    )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)],
        check=True, capture_output=True, text=True,
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    return repo


def _add_worktree(repo: Path, target: Path, branch: str) -> Path:
    _git(repo, "worktree", "add", str(target), "-b", branch, "HEAD")
    return target


def test_decompose_worktree_children_get_own_workspace(kanban_home):
    with kb.connect() as conn:
        root = kb.create_task(conn, title="build the feature", triage=True)
        conn.execute(
            "UPDATE tasks SET workspace_kind='worktree', "
            "workspace_path='/repo/.worktrees/root' WHERE id = ?",
            (root,),
        )
        conn.commit()

        child_ids = kb.decompose_triage_task(
            conn,
            root,
            root_assignee="orchestrator",
            children=[
                {"title": "spec it", "assignee": "alice", "parents": []},
                {"title": "implement it", "assignee": "bob", "parents": [0]},
            ],
            author="decomposer",
        )
        assert child_ids is not None and len(child_ids) == 2

        for cid in child_ids:
            row = conn.execute(
                "SELECT workspace_kind, workspace_path FROM tasks WHERE id = ?",
                (cid,),
            ).fetchone()
            assert row["workspace_kind"] == "worktree"
            # Each child resolves its own <repo>/.worktrees/<child-id> at
            # dispatch; the root's literal path must never be shared.
            assert row["workspace_path"] is None




def test_dead_worktree_remnant_does_not_block_the_next_dispatch(kanban_home, tmp_path):
    """A leftover directory must not make ``git worktree add`` fail forever.

    Measured on the fleet board (t_25a90777): a task completed on 03.09 left
    ``<repo>/.worktrees/<id>`` on disk while the administrative dir behind its
    ``.git`` pointer (``<repo>/.git/worktrees/<id>``) went away. ``git -C``
    then cannot read the directory, ``git worktree repair`` refuses it, and
    ``git worktree add`` — with or without ``--force`` — answers
    ``fatal: '<path>' already exists``. The card was reopened 13 days later and
    re-dispatch died on that wall every single tick.
    """
    repo = _make_repo(tmp_path)
    target = repo / ".worktrees" / "t_dead"
    _add_worktree(repo, target, "wt/t_dead")
    shutil.rmtree(repo / ".git" / "worktrees" / "t_dead")

    # Precondition: the remnant is unreadable AND un-addable-to, i.e. the wall.
    assert subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True,
    ).returncode != 0
    assert "already exists" in subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", str(target), "wt/t_dead"],
        capture_output=True, text=True,
    ).stderr

    kb._ensure_git_worktree(repo, target, "wt/t_dead")

    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert head == "wt/t_dead"
    # Moved aside, never deleted: uncommitted work stays findable.
    moved = sorted(target.parent.glob("t_dead.forlatt-*"))
    assert len(moved) == 1, [str(p) for p in target.parent.iterdir()]
    assert (moved[0] / "README.md").exists()


def test_live_worktree_is_reused_and_nothing_is_moved_aside(kanban_home, tmp_path):
    """The other half: a worktree of this repo is reused untouched."""
    repo = _make_repo(tmp_path)
    target = _add_worktree(repo, repo / ".worktrees" / "t_live", "wt/t_live")
    (target / "wip.txt").write_text("not committed\n", encoding="utf-8")

    kb._ensure_git_worktree(repo, target, "wt/t_live")

    assert (target / "wip.txt").read_text(encoding="utf-8") == "not committed\n"
    assert not list(target.parent.glob("t_live.*")), "a live worktree was touched"


def test_an_occupied_path_is_reported_not_moved(kanban_home, tmp_path):
    """Only a PROVABLY dead remnant is cleared.

    A directory that merely occupies the path — no ``.git`` pointer at all —
    may hold something a human put there, and nothing here can tell. git
    refuses it (``fatal: '<path>' already exists``) and so do we: the occupant
    is left exactly as it was. Measured on git 2.53.0: an existing EMPTY
    directory is accepted by ``git worktree add``, which is why the occupant
    here holds a file.
    """
    repo = _make_repo(tmp_path)
    target = tmp_path / "utenfor" / "t_occupied"
    target.mkdir(parents=True)
    (target / "keep-me.txt").write_text("human data\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="already exists"):
        kb._ensure_git_worktree(repo, target, "wt/t_occupied")

    assert (target / "keep-me.txt").read_text(encoding="utf-8") == "human data\n"
    assert not list(target.parent.glob("t_occupied.*"))


def test_resolve_worktree_falls_back_when_path_occupied(kanban_home, tmp_path):
    repo = _make_repo(tmp_path)
    occupied = _add_worktree(repo, repo / ".worktrees" / "sibling", "wt/sibling")

    with kb.connect() as conn:
        tid = kb.create_task(
            conn,
            title="second sibling",
            workspace_kind="worktree",
            workspace_path=str(occupied),  # inherited shared/stale path
        )
        task = kb.get_task(conn, tid)

    workspace, branch = kb._resolve_worktree_workspace(task)
    assert workspace == (repo / ".worktrees" / tid).resolve()
    assert branch == f"wt/{tid}"
    # The sibling's checkout is untouched, still on its own branch.
    assert (occupied / "README.md").exists()
    head = subprocess.run(
        ["git", "-C", str(occupied), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert head == "wt/sibling"




