"""Bundled-skill maintenance ops: reset, diff, list-modified, opt-out, remove-pristine.
Profile-scoped paths and patchable helpers resolve through ``_ss()`` at call time."""

from pathlib import Path
from typing import List, Optional, Tuple

from tools.skills_sync_optional import _skill_file_list, _ss


def _bundled_state():
    """``(skills_sync, manifest, bundled_dir, {skill_name: bundled_src})`` — shared op preamble."""
    ss = _ss()
    bundled_dir = ss._get_bundled_dir()
    return ss, ss._read_manifest(), bundled_dir, dict(ss._discover_bundled_skills(bundled_dir))


def reset_bundled_skill(name: str, restore: bool = False) -> dict:
    """Reset a bundled skill's manifest tracking so future syncs work normally. A copy that cannot
    be proven to match the version shipped now stays flagged forever because the manifest holds the
    OLD origin hash; clearing the entry breaks that loop — but ONLY when the copy is byte-identical
    to the version shipped now, because that is the only case the next sync re-baselines
    (``_install_new_skill`` compares the hashes and sets no row when they differ). ``restore``
    replaces the user's copy with stock. Returns ``{ok, action, message, synced}``; action is
    manifest_cleared / restored / not_in_manifest / bundled_missing / refused_copy_diverges /
    not_rebaselined / manifest_write_failed.
    """
    ss, manifest, bundled_dir, bundled_by_name = _bundled_state()
    in_manifest = name in manifest
    is_bundled = name in bundled_by_name

    def _fail(action: str, message: str) -> dict:
        return {"ok": False, "action": action, "message": message, "synced": None}

    if not in_manifest and not is_bundled:
        return _fail("not_in_manifest", f"'{name}' is not a tracked bundled skill. Nothing to reset. "
                     f"(Hub-installed skills use `hermes skills uninstall`.)")
    dest = ss._compute_relative_dest(bundled_by_name[name], bundled_dir) if is_bundled else None

    # Step 1 (optional): delete the user's copy so next sync re-copies bundled. Must happen BEFORE manifest
    # deletion so that a failed rmtree does not leave the skill in a manifest-less limbo state (see #34972).
    deleted_user_copy = False
    if restore:  # delete the user's copy BEFORE the manifest so a failed rmtree can't strand it
        if not is_bundled:
            return _fail("bundled_missing", f"'{name}' has no bundled source — manifest entry preserved "
                         f"but cannot restore from bundled (skill was removed upstream).")
        if dest is not None and dest.exists():
            deleted_user_copy = True
            try:
                ss._rmtree_writable(dest)
            except OSError as e:
                return _fail("not_reset", f"Could not delete user copy at {dest}: {e}. "
                             f"Manifest entry preserved — nothing was changed.")
    elif is_bundled and dest is not None and dest.exists():
        # Measured on `github` (t_eb487a72): for a copy that differs from the shipped version the
        # sync takes the _install_new_skill branch, which prints "bundled version shipped but you
        # already have a local skill" and sets NO row — so the flag goes quiet while the skill
        # still ignores upstream changes. That is worse than the flag, so refuse instead of
        # promising a re-baseline that will not happen.
        verdict = ss.explain_flagged_copy(dest, bundled_by_name[name])
        if verdict["state"] != ss.COPY_MATCHES_STOCK:
            return {"ok": False, "action": "refused_copy_diverges", "synced": None,
                    "state": verdict["state"],
                    "message": (f"'{name}' not reset: {verdict['message']}. Clearing the manifest "
                                f"entry would only silence the flag — the next sync keeps your copy "
                                f"and records no new origin row, so this skill would stay pinned at "
                                f"its current content with nothing reporting it. Reconcile the "
                                f"difference, or run `hermes skills reset {name} --restore` to "
                                f"replace your copy with the shipped version.")}
    if in_manifest:
        del manifest[name]
        try:
            ss._write_manifest(manifest)
        except ss.ManifestWriteError as e:
            return _fail("manifest_write_failed", f"Could not clear the manifest entry for '{name}': {e}")
    synced = ss.sync_skills(quiet=True)
    if restore:
        return {"ok": True, "action": "restored", "synced": synced,
                "message": (f"Restored '{name}' from bundled source." if deleted_user_copy
                            else f"Restored '{name}' (no prior user copy, re-copied from bundled).")}
    # Read the outcome back: the promise below is only true when a row for this name now exists.
    row = ss._read_manifest().get(name)

    def _verify_message(message: str) -> dict:
        return {"ok": True, "action": "manifest_cleared", "synced": synced, "message": message}

    if row and dest is not None and dest.exists() and row == ss._dir_hash(dest):
        return _verify_message(
            f"Cleared the manifest entry for '{name}' and re-baselined it against your current copy "
            f"(byte-identical to the shipped version). Future `hermes update` runs accept upstream "
            f"changes to it.")
    if row and dest is not None and not dest.exists():
        return _verify_message(
            f"Cleared the manifest entry for '{name}'. It had no local copy, so the sync re-copied "
            f"the shipped version and recorded it — future `hermes update` runs accept upstream "
            f"changes to it.")
    return {"ok": False, "action": "not_rebaselined", "synced": synced,
            "message": (f"Cleared the manifest entry for '{name}', but the sync wrote no new origin "
                        f"row for it, so `hermes update` still will not re-baseline it. Nothing is "
                        f"recorded about this name now — check `hermes skills list-modified` and the "
                        f"sync output above before assuming it tracks upstream.")}


def list_user_modified_bundled_skills() -> List[dict]:
    """Bundled skills ``hermes update`` keeps because the origin hash cannot be proven (the same
    test the sync loop uses), each with the STATE it is actually in.

    Name-sorted ``{"name", "dest", "bundled_src", "state", "state_message", "state_counts"}``.
    "user-modified" was the old single label, and it was wrong for most of what it caught: a
    stale origin row and an older upstream copy are not edits (t_eb487a72). The states come from
    one bounded read of the checkout's history; where that is unavailable the state is
    ``unproven`` and says so instead of guessing.
    """
    ss = _ss()
    if not (manifest := ss._read_manifest()):
        return []
    bundled_dir = ss._get_bundled_dir()
    modified: List[dict] = []
    for skill_name, skill_dir in ss._discover_bundled_skills(bundled_dir):
        origin_hash = manifest.get(skill_name, "")  # empty = untracked/un-baselined v1: next sync handles it
        dest = ss._compute_relative_dest(skill_dir, bundled_dir)
        if origin_hash and dest.exists() and not ss._matches_origin_hash(dest, origin_hash):
            modified.append({"name": skill_name, "dest": dest, "bundled_src": skill_dir})
    modified.sort(key=lambda e: e["name"])
    history = ss._upstream_blob_index([e["bundled_src"] for e in modified]) if modified else None
    for entry in modified:
        verdict = ss.explain_flagged_copy(entry["dest"], entry["bundled_src"], history=history)
        entry.update(state=verdict["state"], state_message=verdict["message"],
                     state_counts=verdict["counts"])
    return modified


def _read_for_diff(path: Path) -> Tuple[Optional[bytes], Optional[str]]:
    """``(raw_bytes, text)`` for diffing; ``text=None`` for binary, ``(None, None)`` if unreadable."""
    try:
        data = path.read_bytes()
    except OSError:
        return None, None
    try:
        return data, (None if b"\x00" in data else data.decode("utf-8"))
    except UnicodeDecodeError:
        return data, None


def diff_bundled_skill(name: str) -> dict:
    """Diff a user's copy of a bundled skill against stock. Returns ``{ok, name, found, modified,
    message, diffs}``; each diff is ``{"path", "status", "diff"}`` with status modified / added
    (only in user copy) / removed (only in bundled) / binary."""
    import difflib
    ss, _, bundled_dir, bundled_by_name = _bundled_state()

    def _fail(found: bool, message: str) -> dict:
        return {"ok": False, "name": name, "found": found, "modified": False, "diffs": [], "message": message}

    if (bundled_src := bundled_by_name.get(name)) is None:
        return _fail(False, f"'{name}' is not a tracked bundled skill (no stock version to "
                     f"diff against). Hub-installed skills use `hermes skills inspect`.")
    dest = ss._compute_relative_dest(bundled_src, bundled_dir)
    if not dest.exists():
        return _fail(True, f"No local copy of '{name}' found at {dest}.")
    user_files = set(_skill_file_list(dest))
    stock_files = set(_skill_file_list(bundled_src))
    diffs: List[dict] = []
    for rel in sorted(user_files | stock_files):
        if rel not in stock_files:
            diffs.append({"path": rel, "status": "added", "diff": f"+ only in your copy: {rel}"})
            continue
        if rel not in user_files:
            diffs.append({"path": rel, "status": "removed", "diff": f"- only in stock: {rel}"})
            continue
        user_bytes, user_text = _read_for_diff(dest / rel)
        stock_bytes, stock_text = _read_for_diff(bundled_src / rel)
        if user_text is None or stock_text is None:  # a binary side: report only if bytes differ
            if user_bytes != stock_bytes:
                diffs.append({"path": rel, "status": "binary", "diff": "<binary file differs>"})
        elif user_text != stock_text:
            text = "".join(difflib.unified_diff(
                stock_text.splitlines(keepends=True), user_text.splitlines(keepends=True),
                fromfile=f"stock/{rel}", tofile=f"yours/{rel}"))
            diffs.append({"path": rel, "status": "modified", "diff": text})
    message = (f"'{name}' differs from the stock version in {len(diffs)} file(s)." if diffs
               else f"'{name}' matches the stock version.")
    verdict = ss.explain_flagged_copy(dest, bundled_src)
    return {"ok": True, "name": name, "found": True, "modified": bool(diffs), "diffs": diffs,
            "message": message, "state": verdict["state"], "state_message": verdict["message"]}


_OPT_OUT_MESSAGES = {  # (enabled, changed) -> message
    (True, True): "Opted out of bundled skills. Future install / update / sync runs will not seed bundled skills into this profile.",
    (True, False): "Already opted out — marker was already present.",
    (False, True): "Opted back in. The next `hermes update` (or `hermes skills opt-in --sync`) will re-seed bundled skills.",
    (False, False): "Not opted out — no marker to remove."}


def set_bundled_skills_opt_out(enabled: bool) -> dict:
    """Toggle the .no-bundled-skills marker (on-disk half of ``hermes skills opt-out`` / ``opt-in``;
    removing present skills is ``remove_pristine_bundled_skills``)."""
    ss = _ss()
    marker = ss._hermes_home() / ss.NO_BUNDLED_SKILLS_MARKER
    existed = marker.exists()
    try:
        if enabled:
            ss._hermes_home().mkdir(parents=True, exist_ok=True)
            marker.write_text(
                "This profile opted out of bundled-skill seeding (`hermes skills opt-out`).\n"
                "Delete this file to re-enable sync on the next `hermes update`.\n",
                encoding="utf-8")
        elif existed:
            marker.unlink()
    except OSError as e:
        return {"ok": False, "changed": False, "marker": str(marker),
                "message": f"Could not update opt-out marker at {marker}: {e}"}
    changed = enabled != existed
    return {"ok": True, "changed": changed, "marker": str(marker), "message": _OPT_OUT_MESSAGES[(enabled, changed)]}


def remove_pristine_bundled_skills(dry_run: bool = False) -> dict:
    """Delete bundled skills that are manifest-tracked, still in the bundled source AND
    byte-identical to the origin hash; everything else lands in ``skipped``. Removed skills lose
    their manifest entry so a later opt-in re-seed treats them as new.
    Returns ``{ok, removed, skipped: [{name, reason}], dry_run, message}``."""
    ss, manifest, bundled_dir, bundled_by_name = _bundled_state()
    removed: List[str] = []
    skipped: List[dict] = []
    for name, origin_hash in sorted(manifest.items()):
        src = bundled_by_name.get(name)
        if src is None:
            skipped.append({"name": name, "reason": "no bundled source (removed upstream)"})
            continue
        dest = ss._compute_relative_dest(src, bundled_dir)
        if not dest.exists():
            if not dry_run:  # already gone from disk; forget the stale manifest entry
                manifest.pop(name, None)
            continue
        if not ss._matches_origin_hash(dest, origin_hash):
            skipped.append({"name": name, "reason": "copy not provably pristine (kept)"})
            continue
        if not dry_run:
            try:
                ss._rmtree_writable(dest)
            except OSError as e:
                skipped.append({"name": name, "reason": f"delete failed: {e}"})
                continue
            manifest.pop(name, None)
        removed.append(name)
    if not dry_run and removed:
        try:
            ss._write_manifest(manifest)
        except ss.ManifestWriteError as e:
            return {"ok": False, "removed": removed, "skipped": skipped, "dry_run": dry_run,
                    "message": (f"Removed {len(removed)} pristine bundled skill(s), but the manifest "
                                f"could not be updated ({e}); their entries are still recorded, so "
                                f"the next sync treats them as user-deleted.")}
    verb = "Would remove" if dry_run else "Removed"
    return {"ok": True, "removed": removed, "skipped": skipped, "dry_run": dry_run,
            "message": f"{verb} {len(removed)} pristine bundled skill(s); kept {len(skipped)}."}
