"""Guard: every `hermes update` path that reports kept bundled skills must
also tell the user how to find them.

`hermes update` keeps (does not overwrite) bundled skills that are not
tracking upstream and prints a ``~ N not tracking upstream (kept)`` count.
The count line must point the user at ``hermes skills list-modified`` so the
count is actionable — otherwise they may never learn the discovery command
exists.

This is an *invariant* test (the notices must agree), not a literal
snapshot: it asserts the relationship "count line ⇒ discovery hint", so it
keeps holding if the wording is reworded, as long as the hint stays glued to
the count line.

The wording itself is also guarded (t_3bb84fd8): the old label
"user-modified" was measured to be false for doors that are byte-identical
with the shipped version, and the report must not revive it.
"""

import re
from pathlib import Path

import hermes_cli.main as main_mod
import hermes_cli.update_cmd as update_mod
import hermes_cli.update_cmd_maint as update_maint_mod
import hermes_cli.update_cmd_zip as update_zip_mod


_COUNT_RE = re.compile(r"not tracking upstream \(kept\)")
_HINT_RE = re.compile(r"hermes skills list-modified")


def _source_lines() -> list[str]:
    # The update pipeline was extracted to hermes_cli/update_cmd.py and then
    # split into update_cmd_*.py; scan every home of the notice.
    return [
        line
        for mod in (main_mod, update_mod, update_maint_mod, update_zip_mod)
        for line in Path(mod.__file__).read_text(encoding="utf-8").splitlines()
    ]


def test_every_kept_skills_notice_points_at_list_modified():
    lines = _source_lines()
    count_sites = [i for i, ln in enumerate(lines) if _COUNT_RE.search(ln)]

    # The notice must exist somewhere (guard against it being deleted outright),
    # but we deliberately do NOT assert a fixed *count* of sites: consolidating
    # the duplicated print paths into a shared helper is a welcome refactor and
    # must not fail this test. The invariant is per-site, not how many sites.
    assert count_sites, (
        "no 'not tracking upstream (kept)' notice found — the update "
        "summary that surfaces kept bundled skills appears to have been removed"
    )

    for idx in count_sites:
        # The count print and its discovery hint sit on adjacent lines; allow a
        # small window so wording/formatting tweaks don't break the check.
        window = "\n".join(lines[idx : idx + 5])
        assert _HINT_RE.search(window), (
            "a 'not tracking upstream (kept)' notice near line "
            f"{idx + 1} does not point users at "
            "`hermes skills list-modified` within the following lines — the "
            "update paths have drifted apart again:\n" + window
        )


def test_sync_report_never_calls_kept_copies_user_modified(monkeypatch, capsys):
    """The report must not reuse the old 'user-modified' label.

    t_3bb84fd8: 20 of 30 flagged doors were byte-identical with the shipped
    version — the label "user-modified (kept)" was measured to be a lie for
    them. The report must name the measured state instead, and the word
    'user-modified' must not appear for such a door at all.
    """
    from tools import skills_sync

    names = ["alpha", "beta"]
    reasons = {
        "alpha": skills_sync.COPY_MATCHES_STOCK,  # byte-identical to shipped
        "beta": skills_sync.COPY_BEHIND_UPSTREAM,  # an older upstream revision
    }
    monkeypatch.setattr(
        skills_sync,
        "sync_skills",
        lambda quiet=True: {
            "copied": [],
            "updated": [],
            "user_modified": names,
            "user_modified_reasons": reasons,
            "cleaned": [],
            "relocated": [],
            "manifest_error": "",
        },
    )
    update_maint_mod._print_bundled_skills_sync_report()
    out = capsys.readouterr().out
    assert "not tracking upstream (kept)" in out
    assert "user-modified" not in out
    assert "byte-identical to the shipped version" in out
    assert "behind upstream" in out
