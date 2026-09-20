"""Tests for discovering and diffing user-modified bundled skills.

`hermes update` keeps (does not overwrite) bundled skills the user edited
locally, but historically only printed a *count* — there was no way to find
which skills, or see what changed. These tests cover the two helpers that close
that gap, exercising the real sync pipeline (no mocks of the comparison logic):

* ``list_user_modified_bundled_skills()`` — the discovery half of the exact
  test the sync loop uses to decide what to skip.
* ``diff_bundled_skill()`` — a unified diff of the user copy vs the stock copy.

Revert already exists (``reset_bundled_skill``); the last tests confirm it
clears the modified state so the two stay consistent — and that it *refuses*
when the copy differs from the shipped version, because clearing the entry
there writes no new origin row (the flag goes quiet while the skill stays
pinned; t_eb487a72). The copy's state, not the old blanket "you've edited", is
what the reader text has to name.
"""

import io
from contextlib import ExitStack
from unittest.mock import patch

from tools.skills_sync import sync_skills
from tools.skills_sync_bundled_ops import (
    reset_bundled_skill,
    list_user_modified_bundled_skills,
    diff_bundled_skill,
)


def _make_bundled(tmp_path):
    """A fake bundled skills tree with one skill: category/foo."""
    bundled = tmp_path / "bundled_skills"
    foo = bundled / "category" / "foo"
    foo.mkdir(parents=True)
    (foo / "SKILL.md").write_text("---\nname: foo\n---\n# Foo Skill\n")
    (foo / "helper.py").write_text("print('stock')\n")
    return bundled


def _patches(bundled, skills_dir, manifest_file):
    stack = ExitStack()
    stack.enter_context(
        patch("tools.skills_sync._get_bundled_dir", return_value=bundled)
    )
    stack.enter_context(
        patch(
            "tools.skills_sync._get_optional_dir",
            return_value=bundled.parent / "optional-skills",
        )
    )
    stack.enter_context(patch("tools.skills_sync.SKILLS_DIR", skills_dir))
    stack.enter_context(patch("tools.skills_sync.MANIFEST_FILE", manifest_file))
    return stack


def _env(tmp_path):
    bundled = _make_bundled(tmp_path)
    skills_dir = tmp_path / "user_skills"
    manifest_file = skills_dir / ".bundled_manifest"
    return bundled, skills_dir, manifest_file


def test_pristine_skill_is_not_listed_as_modified(tmp_path):
    bundled, skills_dir, manifest_file = _env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        sync_skills(quiet=True)
        assert list_user_modified_bundled_skills() == []


def test_reset_clears_modified_state(tmp_path):
    """Revert (existing) and discovery (new) must agree: after reset, not modified."""
    bundled, skills_dir, manifest_file = _env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        sync_skills(quiet=True)
        (skills_dir / "category" / "foo" / "helper.py").write_text("print('mine')\n")
        assert [m["name"] for m in list_user_modified_bundled_skills()] == ["foo"]

        # Restore from the stock source, then it must no longer be flagged.
        result = reset_bundled_skill("foo", restore=True)
        assert result["ok"] is True
        assert list_user_modified_bundled_skills() == []


def _capture_console():
    from rich.console import Console
    buf = io.StringIO()
    return Console(file=buf, width=200, no_color=True, highlight=False), buf


def _stale_origin_env(tmp_path):
    """The shaped state from t_eb487a72: the copy is the shipped version, the manifest row is old."""
    bundled, skills_dir, manifest_file = _env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        sync_skills(quiet=True)  # records the real origin, then we age the row
    manifest_file.write_text("foo:OLDORIGIN0000000000000000000000000000\n", encoding="utf-8")
    return bundled, skills_dir, manifest_file


def test_copy_identical_to_stock_is_not_described_as_an_edit(tmp_path):
    """(b) A copy byte-identical to upstream, with an older origin row, is not "you've edited it"."""
    bundled, skills_dir, manifest_file = _stale_origin_env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        entries = list_user_modified_bundled_skills()
        console, buf = _capture_console()
        from hermes_cli.skills_hub import do_list_modified
        do_list_modified(console=console)

    assert [e["state"] for e in entries] == ["copy_matches_stock"]
    assert "byte-identical" in entries[0]["state_message"]

    text = buf.getvalue()
    assert "foo" in text
    assert "the copy is the shipped version" in text
    # The old wording claimed an edit; the new one may only say the copy was NOT edited.
    assert "you've edited" not in text
    assert "user-modified bundled skill(s)" not in text
    assert "1 bundled skill(s) not tracking upstream" in text


def test_sync_says_byte_identical_instead_of_user_modified(tmp_path, capsys):
    """The sync's own per-name line was the other place the wrong claim was made."""
    bundled, skills_dir, manifest_file = _stale_origin_env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        result = sync_skills(quiet=False)

    out = capsys.readouterr().out
    assert "foo (copy is byte-identical to the version shipped now" in out
    assert "user-modified" not in out
    # Behaviour is unchanged: the copy is still skipped, only the reason is named.
    assert result["user_modified"] == ["foo"]
    assert result["user_modified_reasons"]["foo"] == "copy_matches_stock"


def test_reset_refuses_a_differing_copy_instead_of_promising_a_rebaseline(tmp_path):
    """(c) Measured on `github`: reset goes quiet *and* re-baselines nothing. Refuse instead."""
    bundled, skills_dir, manifest_file = _env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        sync_skills(quiet=True)
        (skills_dir / "category" / "foo" / "helper.py").write_text("print('mine')\n")
        before = manifest_file.read_text(encoding="utf-8")

        result = reset_bundled_skill("foo", restore=False)

        after = manifest_file.read_text(encoding="utf-8")

    assert result["ok"] is False
    assert result["action"] == "refused_copy_diverges"
    assert "not reset" in result["message"]
    assert "silence the flag" in result["message"]
    assert "re-baseline against your current copy" not in result["message"]
    # Nothing went quiet and nothing was touched.
    assert before == after
    assert (skills_dir / "category" / "foo" / "helper.py").read_text() == "print('mine')\n"


def test_reset_message_is_true_when_the_copy_is_the_shipped_version(tmp_path):
    bundled, skills_dir, manifest_file = _stale_origin_env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        result = reset_bundled_skill("foo", restore=False)
        assert result["ok"] is True
        assert result["action"] == "manifest_cleared"
        assert "re-baselined it against your current copy" in result["message"]
        assert list_user_modified_bundled_skills() == []


def test_diff_names_the_state_and_does_not_promise_a_reset(tmp_path):
    bundled, skills_dir, manifest_file = _env(tmp_path)
    with _patches(bundled, skills_dir, manifest_file):
        sync_skills(quiet=True)
        (skills_dir / "category" / "foo" / "helper.py").write_text("print('mine')\n")

        result = diff_bundled_skill("foo")
        console, buf = _capture_console()
        from hermes_cli.skills_hub import do_diff
        do_diff("foo", console=console)

    assert result["state"]
    assert result["state_message"]
    text = buf.getvalue()
    assert "State:" in text
    assert "refuses while your copy differs" in text
