#!/usr/bin/env python3
"""Skills Sync -- manifest-based seeding and updating of bundled skills. Copies repo skills/ into
~/.hermes/skills/, tracking each synced skill's origin hash in .bundled_manifest (v2 "name:hash"
lines; v1 plain names auto-migrate). NEW skills are copied and recorded; EXISTING skills update
only when bundled changed AND the user copy still matches the origin hash (else user-customized
-> SKIP); user-DELETED skills are not re-added; upstream-REMOVED ones leave the manifest.

Three properties this module has to keep honest (t_eb487a72): every manifest write is read back
and compared (``ManifestWriteError``), an UNREADABLE manifest is an error rather than an empty
one (``ManifestReadError``), and a skipped copy is described by the state it is actually in —
stale origin row, behind upstream, or local content — never as "you edited it"."""

import hashlib
import logging
import os
import shutil
import stat
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

# Force UTF-8 stdout/stderr: GBK-style Windows locales can't encode the glyphs
# printed here (✓ ↑ →), and install.ps1 parses this script's stdout as UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        with suppress(ValueError, TypeError):
            _stream.reconfigure(encoding="utf-8", errors="replace")
from hermes_constants import get_bundled_skills_dir, get_hermes_home, get_optional_skills_dir
from agent.skill_utils import ESSENTIAL_SKILLS, is_excluded_skill_path
from tools.skill_usage import _read_skill_name, read_suppressed_names
from tools.skills_sync_optional import (
    _backfill_optional_provenance, _ignore_runtime_cache, _is_runtime_cache, _read_hub_install_paths,
    _skill_file_list,
)
from utils import atomic_write_text

logger = logging.getLogger(__name__)

HERMES_HOME = get_hermes_home()
SKILLS_DIR = HERMES_HOME / "skills"
MANIFEST_FILE = SKILLS_DIR / ".bundled_manifest"

# Import-time snapshots backing the call-time accessors: long-lived multi-profile runtimes
# retarget HERMES_HOME after import, and frozen constants would resolve (and for
# reset_bundled_skill() DELETE) against the wrong profile. Accessors honor an explicitly
# patched module global and otherwise re-resolve on every call.
# Same bug class and same fix as skills_tool (f8723c478) and skill_manager_tool (c6a3d412d): long-lived
# multi-profile runtimes (Dashboard console, TUI/Desktop backend, cron, kanban workers) import this module
# once under the launch HERMES_HOME and later scope requests to a different profile via
# set_hermes_home_override(). See #65828.
_HERMES_HOME_AT_IMPORT = HERMES_HOME
_SKILLS_DIR_AT_IMPORT = SKILLS_DIR
_MANIFEST_FILE_AT_IMPORT = MANIFEST_FILE


def _live(configured, at_import: Path, fallback) -> Path:
    """The patched module global if it changed since import, else the live value."""
    return Path(configured) if Path(configured) != at_import else fallback()


def _hermes_home() -> Path:
    return _live(HERMES_HOME, _HERMES_HOME_AT_IMPORT, get_hermes_home)


def _skills_dir() -> Path:
    return _live(SKILLS_DIR, _SKILLS_DIR_AT_IMPORT, lambda: _hermes_home() / "skills")


def _manifest_file() -> Path:
    return _live(MANIFEST_FILE, _MANIFEST_FILE_AT_IMPORT, lambda: _skills_dir() / ".bundled_manifest")


# Written by `hermes profile create --no-skills` / installer `--no-skills`: sync seeds only
# essential skills. Mirrors hermes_cli.profiles.NO_BUNDLED_SKILLS_MARKER (no CLI import here).
NO_BUNDLED_SKILLS_MARKER = ".no-bundled-skills"


def _get_bundled_dir() -> Path:  # HERMES_BUNDLED_SKILLS env first, then repo-relative
    return get_bundled_skills_dir(Path(__file__).parent.parent / "skills")


def _get_optional_dir() -> Path:
    return get_optional_skills_dir(Path(__file__).parent.parent / "optional-skills")


def _rel_skills_posix(path: Path) -> str:
    return path.relative_to(_skills_dir()).as_posix()


def _iter_skill_mds(root: Path, sort: bool = False) -> Iterator[Path]:
    """Yield every non-excluded SKILL.md under ``root`` (nothing when it does not exist)."""
    found = root.rglob("SKILL.md") if root.exists() else iter(())
    for skill_md in sorted(found) if sort else found:
        if not is_excluded_skill_path(skill_md):
            yield skill_md


def _iter_active_skill_mds(sort: bool = False) -> Iterator[Path]:
    """Yield every non-excluded SKILL.md in the user's skills tree."""
    return _iter_skill_mds(_skills_dir(), sort)


def _build_external_skill_index() -> Set[str]:
    """Names (directory and frontmatter) of every skill provided by external_dirs,
    so sync_skills never shadows an externally-delegated skill."""
    from agent.skill_utils import get_external_skills_dirs, _external_dirs_cache_clear
    _external_dirs_cache_clear()  # so a config edit (or a test patch) is seen
    external_names: Set[str] = set()
    for ext_dir in get_external_skills_dirs():
        for skill_md in _iter_skill_mds(ext_dir):
            external_names.update({skill_md.parent.name, _read_skill_name(skill_md, "")})
    external_names.discard("")
    return external_names


class ManifestReadError(RuntimeError):
    """The manifest exists but could not be read — NOT the same as an absent manifest."""


class ManifestWriteError(RuntimeError):
    """A manifest write did not land, or did not read back as what was written."""


def _parse_manifest_text(text: str) -> Dict[str, str]:
    """v1/v2 manifest text -> ``{skill_name: origin_hash}`` (v1 plain names keep an empty hash)."""
    pairs = (line.partition(":") for line in map(str.strip, text.splitlines()) if line)
    return {name.strip(): hash_val.strip() for name, _, hash_val in pairs}


def _manifest_mismatch(entries: Dict[str, str], written_text: str) -> str:
    """One line describing how the file on disk differs from what we meant to write."""
    on_disk = _parse_manifest_text(written_text)
    missing = sorted(set(entries) - set(on_disk))
    extra = sorted(set(on_disk) - set(entries))
    wrong = sorted(n for n in set(entries) & set(on_disk) if entries[n] != on_disk[n])
    first = next(iter(missing + extra + wrong), "")
    return (f"{len(missing)} missing row(s), {len(extra)} unexpected row(s), "
            f"{len(wrong)} wrong hash(es)" + (f"; first: {first!r}" if first else ""))


def _read_manifest() -> Dict[str, str]:
    """``{skill_name: origin_hash}``; v1 plain-name lines get an empty hash (migrates next sync).

    A MISSING manifest is legitimately empty. An UNREADABLE one is not, and must not be reported
    as one: the empty dict makes every bundled skill look "new", so the caller silently
    re-baselines the lot. Raise instead, so the failure can be said out loud (t_eb487a72).
    """
    path = _manifest_file()
    try:
        if not path.exists():
            return {}
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Skills manifest %s exists but could not be read: %s", path, e)
        raise ManifestReadError(
            f"skills manifest {path} exists but could not be read ({e}). Refusing to treat it as "
            f"empty — that would re-baseline every bundled skill. Fix the file's permissions and "
            f"retry, or delete it to deliberately start from an empty manifest.") from e
    return _parse_manifest_text(text)


def _read_suppressed_names() -> set:
    """Built-in skills the curator pruned — must NOT be re-seeded (tests patch this name)."""
    return read_suppressed_names()


def _write_manifest(entries: Dict[str, str]) -> None:
    """Atomic v2 write, read back and compared; raises ``ManifestWriteError`` on any deviation.

    A write nobody reads back is not a write. In the 2026-09-10 update, phase 1 reported
    ``↑ 27 updated`` and phase 2 of the SAME run read those 27 as user-modified: the rows never
    landed, so every one of those "updated" lines was wrong (t_eb487a72). Callers that report
    per-name success must therefore treat a raise here as "those names are not recorded" — see
    ``sync_skills()``, which refuses to report them as updated.
    """
    path = _manifest_file()
    from hermes_constants import mkdir_under_hermes_home
    mkdir_under_hermes_home(path.parent)
    data = "".join(f"{n}:{h}\n" for n, h in sorted(entries.items()))
    try:
        atomic_write_text(path, data, tmp_prefix=".bundled_manifest_", preserve_mode=True)
        written_text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write skills manifest %s: %s", path, e, exc_info=True)
        raise ManifestWriteError(f"could not write {path}: {e}") from e
    if written_text != data:
        logger.error("Skills manifest %s did not read back as written: %s", path,
                     _manifest_mismatch(entries, written_text))
        raise ManifestWriteError(
            f"{path} did not read back as written ({_manifest_mismatch(entries, written_text)})")
    logger.debug("Skills manifest %s written and verified (%d rows)", path, len(entries))


def _discover_bundled_skills(bundled_dir: Path) -> List[Tuple[str, Path]]:
    """``(skill_name, skill_dir)`` per SKILL.md under the bundled dir. Exclusions are evaluated
    relative to the bundled tree: the install prefix itself may contain ``venv``/``site-packages``
    (which once made wheel installs discover zero skills)."""
    if not bundled_dir.exists():
        return []
    return [
        (_read_skill_name(md, md.parent.name), md.parent)
        for md in bundled_dir.rglob("SKILL.md")
        if not is_excluded_skill_path(md.relative_to(bundled_dir), root=bundled_dir)]


def _compute_relative_dest(skill_dir: Path, bundled_dir: Path) -> Path:
    """Destination preserving category structure (bundled/mlops/axolotl -> skills/mlops/axolotl)."""
    return _skills_dir() / skill_dir.relative_to(bundled_dir)


def _dir_hash(directory: Path, *, include_runtime_cache: bool = False) -> str:
    """MD5 of package paths/content, excluding generated runtime state.

    The legacy option is only for proving an exact pre-filter origin match.
    Keep the original path encoding so clean existing manifests remain valid.
    """
    hasher = hashlib.md5()
    with suppress(OSError):
        for fpath in sorted(directory.rglob("*")):
            if (include_runtime_cache or not _is_runtime_cache(fpath, directory)) and fpath.is_file():
                hasher.update(str(fpath.relative_to(directory)).encode("utf-8"))
                hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


def _matches_origin_hash(directory: Path, origin_hash: str, user_hash: Optional[str] = None) -> bool:
    """Prove unchanged package ownership against a clean OR exact legacy hash.

    Never re-baseline a differing package merely because it contains a cache:
    if legacy cached bytes changed/disappeared, the old origin cannot be proven.
    A genuinely edited package must remain protected in that case.
    """
    if not origin_hash:
        return False
    current = _dir_hash(directory) if user_hash is None else user_hash
    return current == origin_hash or _dir_hash(directory, include_runtime_cache=True) == origin_hash


# ---- Why a bundled copy is flagged (three states, not one) --------------------------------
# `list-modified` said "bundled skills you've edited", but all it tests is "the origin hash
# cannot be proven" — which is equally true of a copy nobody touched. Measured in Morten's home
# 2026-09-20 (this code path, live manifest vs the vendored tree the copies were synced from):
# of 29 flagged names, 19 were byte-identical to the version shipped that day, 7 held older
# upstream content, and 3 held content no upstream revision has (github, hermes-agent,
# sdlc-review) — t_eb487a72. So the reader names the state it can see; "you've edited" is false
# for the first two.
COPY_MATCHES_STOCK = "copy_matches_stock"  # (i) stale origin row; the copy IS the shipped version
COPY_BEHIND_UPSTREAM = "behind_upstream"   # (ii) the copy holds an older upstream revision
COPY_LOCALLY_EDITED = "locally_edited"     # (iii) the copy holds content no upstream revision has
COPY_UNPROVEN = "unproven"                 # differs, and no upstream history here to tell ii from iii


def _blob_sha(data: bytes) -> str:
    """git's blob object id for these bytes — comparable with ``git log --raw`` output."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _git(repo_dir: Path, *args: str, timeout: float) -> Optional["subprocess.CompletedProcess"]:
    """Run git read-only against *repo_dir*; None when git is absent, refuses or times out.

    ``core.abbrev=40`` is not cosmetic: ``git log --raw`` abbreviates object names by default, and
    the shas printed here are compared against locally computed FULL blob ids.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        return subprocess.run(["git", "-C", str(repo_dir), "-c", "core.quotePath=false",
                               "-c", "core.abbrev=40", *args],
                              capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError):
        return None


def _upstream_blob_index(skill_dirs: Sequence[Path]) -> dict:
    """``{git_path: {blob_sha}}`` — every blob any reachable revision holds at that path.

    ``{available, reason, blobs, root}``. Read-only and tree-only (``--raw`` never needs blob
    contents), so it stays offline even on a partial ``blob:none`` clone; the copy itself is
    hashed locally with ``_blob_sha``. The revisions compared against are HEAD plus the tracking
    refs of the ``upstream`` remote when one is configured — a fork's own ``origin`` is not
    upstream — else ``origin``'s. No git, no checkout, or no reachable revision => ``available``
    stays False and the caller must say "cannot tell" rather than guess.
    """
    result: dict = {"available": False, "reason": "", "blobs": {}, "root": None}
    dirs = [d for d in skill_dirs if d]
    if not dirs:
        return result
    root = _git_root(dirs[0])
    if root is None:
        result["reason"] = "the bundled skills are not inside a git checkout"
        return result
    result["root"] = root
    fmt = _git(root, "rev-parse", "--show-object-format", timeout=10)
    if fmt is not None and fmt.returncode == 0 and fmt.stdout.strip() not in ("", "sha1"):
        result["reason"] = f"git object format is {fmt.stdout.strip()}, not sha1"
        return result
    refs = ["HEAD"]
    for remote in ("upstream", "origin"):
        rr = _git(root, "for-each-ref", "--format=%(refname)", f"refs/remotes/{remote}/", timeout=15)
        if rr is not None and rr.returncode == 0 and rr.stdout.split():
            refs += rr.stdout.split()
            break
    paths = []
    for d in dirs:
        try:
            paths.append(d.relative_to(root).as_posix())
        except ValueError:  # bundled dir outside the checkout: no history to read for it
            result["reason"] = f"{d} is outside the checkout at {root}"
            return result
    r = _git(root, "log", "--raw", "--no-renames", "--format=%H", *refs, "--", *paths, timeout=90)
    if r is None or r.returncode != 0:
        result["reason"] = "git could not read this checkout's history"
        return result
    blobs: Dict[str, Set[str]] = {}
    for line in r.stdout.splitlines():
        if not line.startswith(":"):  # commit header, or a line git could not resolve as raw
            continue
        meta, _, path = line[1:].partition("\t")
        fields = meta.split()
        if not path or len(fields) < 4:  # ":<old_mode> <new_mode> <old_sha> <new_sha> <status>"
            continue
        for sha in fields[2:4]:
            if sha.strip("0"):  # 0{40} is the null side of an add/delete
                if len(sha) != 40:  # an abbreviated id can never match a full local blob id
                    result["reason"] = f"git returned abbreviated object ids ({sha!r})"
                    return result
                blobs.setdefault(path, set()).add(sha)
    if not blobs:
        result["reason"] = f"no reachable revision touches the {len(paths)} bundled path(s)"
        return result
    result.update(available=True, reason="", blobs=blobs)
    return result


def _git_root(path: Path) -> Optional[Path]:
    """Toplevel of the checkout *path* lives in, or None when it is not in a git work tree."""
    probe = path if path.is_dir() else path.parent
    r = _git(probe, "rev-parse", "--show-toplevel", timeout=10)
    if r is None or r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip().splitlines()[0])


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _copy_content_in_history(history: dict, stock_src: Path, rel: str, copy_file: Path) -> bool:
    """Does *copy_file*'s exact content exist at ``<stock_src>/<rel>`` in any reachable revision?"""
    root = history.get("root")
    if not root:
        return False
    try:
        git_path = (stock_src.relative_to(root) / rel).as_posix()
    except ValueError:
        return False
    try:
        return _blob_sha(copy_file.read_bytes()) in history["blobs"].get(git_path, ())
    except OSError:
        return False


def explain_flagged_copy(dest: Path, stock_src: Path, *, history: Optional[dict] = None) -> dict:
    """Say WHICH of the three flagged states *dest* is in, given the stock version *stock_src*.

    Returns ``{state, message, counts, history_available}``; counts are
    ``{identical, upstream, local, only_in_stock}`` over the skill's file list. States:
    (i) ``COPY_MATCHES_STOCK`` — the copy is today's shipped version, only the manifest row is old
    (nothing of the user's); (ii) ``COPY_BEHIND_UPSTREAM`` — the copy is older upstream content;
    (iii) ``COPY_LOCALLY_EDITED`` — the copy holds content no upstream revision has. When the two
    cannot be told apart (no upstream history) the answer is ``COPY_UNPROVEN``, never a guess.
    """
    counts = {"identical": 0, "upstream": 0, "local": 0, "only_in_stock": 0}
    if _dir_hash(dest) == _dir_hash(stock_src):
        return {"state": COPY_MATCHES_STOCK, "counts": counts, "history_available": True,
                "message": ("your copy is byte-identical to the version shipped now "
                            "(the manifest's origin row is an older revision) — nothing of yours "
                            "is in it")}
    copy_files = set(_skill_file_list(dest))
    stock_files = set(_skill_file_list(stock_src))
    if history is None:
        history = _upstream_blob_index([stock_src])
    history_available = bool(history.get("available"))
    for rel in sorted(copy_files | stock_files):
        if rel not in copy_files:
            counts["only_in_stock"] += 1
            continue
        if rel in stock_files and _same_bytes(dest / rel, stock_src / rel):
            counts["identical"] += 1
            continue
        if history_available and _copy_content_in_history(history, stock_src, rel, dest / rel):
            counts["upstream"] += 1  # this content IS an upstream revision of this path
        else:
            counts["local"] += 1
    if not history_available:
        return {"state": COPY_UNPROVEN, "counts": counts, "history_available": False,
                "message": (f"your copy differs from the version shipped now "
                            f"({history.get('reason', 'no upstream history available')}) — an older "
                            f"upstream copy cannot be told from your own edit here")}
    if counts["local"]:
        return {"state": COPY_LOCALLY_EDITED, "counts": counts, "history_available": True,
                "message": (f"your copy holds content that no upstream revision has "
                            f"({counts['local']} file(s)"
                            + (f"; {counts['upstream']} more file(s) are older upstream content"
                               if counts["upstream"] else "") + ")")}
    if counts["only_in_stock"]:
        # A file the copy does not have: upstream added it in a newer revision, OR the user
        # deleted it. Those are opposites, and this read cannot tell them apart — say so instead
        # of claiming "nothing of your own is in it" (a deletion is something of the user's).
        return {"state": COPY_UNPROVEN, "counts": counts, "history_available": True,
                "message": (f"your copy is missing {counts['only_in_stock']} file(s) the shipped "
                            f"version has — either an older upstream revision, or files you "
                            f"removed; `hermes skills diff` shows which")}
    if counts["upstream"]:
        return {"state": COPY_BEHIND_UPSTREAM, "counts": counts, "history_available": True,
                "message": (f"your copy holds older upstream content ({counts['upstream']} file(s) "
                            f"match an upstream revision) — nothing of your own is in it")}
    return {"state": COPY_UNPROVEN, "counts": counts, "history_available": True,
            "message": "your copy differs from the version shipped now, but no differing file was "
                       "identified — treating the difference as unexplained"}


def _move_dir(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def _copy_dir(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=_ignore_runtime_cache)


def _recover_renamed_skill(st: "_SyncState", skill_name: str, dest: Path) -> Optional[str]:
    """Move a bundled skill's stale copy to its new canonical path after an upstream RENAME /
    RECATEGORIZATION (else it is misread as user-deleted and stranded forever). Only a copy
    byte-identical to the origin hash — proof *we* placed it — moves. Returns rel source path."""
    origin_hash = st.manifest.get(skill_name, "")
    if not origin_hash:
        return None
    if st.active_index is None:  # by frontmatter name
        st.active_index = {}
        for md in _iter_active_skill_mds():
            st.active_index.setdefault(_read_skill_name(md, md.parent.name), []).append(md.parent)
        st.hub_paths = _read_hub_install_paths()
    for candidate in st.active_index.get(skill_name, []):
        if candidate == dest or not candidate.is_dir():
            continue
        try:
            rel = _rel_skills_posix(candidate)
        except ValueError:
            continue
        if rel in st.hub_paths:  # the hub owns its install paths
            continue
        if not _matches_origin_hash(candidate, origin_hash):  # moving a customized copy would edit user work
            st.say(
                f"  ⚠ {skill_name}: upstream moved this skill to {_rel_skills_posix(dest)}, but your "
                f"modified copy at {rel} was kept — it will not receive updates. "
                f"Run `hermes skills reset {skill_name} --restore` to move to the new location.")
            continue
        try:
            _move_dir(candidate, dest)
        except OSError:
            logger.warning("Could not relocate renamed skill %s -> %s", candidate, dest, exc_info=True)
            return None
        logger.info("Relocated renamed bundled skill: %s -> %s", candidate, dest)
        st.say(f"  → {skill_name} (moved {rel} → {_rel_skills_posix(dest)})")
        return rel
    return None


@dataclass
class _SyncState:
    """Mutable accumulator threaded through one sync_skills() run."""
    manifest: Dict[str, str]
    quiet: bool
    skipped: int = 0
    copied: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    user_modified: List[str] = field(default_factory=list)
    user_modified_paths: Dict[str, Tuple[Path, Path]] = field(default_factory=dict)  # name -> (copy, stock)
    suppressed: List[str] = field(default_factory=list)
    relocated: List[str] = field(default_factory=list)
    shadowed_by_external: List[str] = field(default_factory=list)
    active_index: Optional[Dict[str, List[Path]]] = None  # rename-recovery indexes are expensive on
    hub_paths: Set[str] = field(default_factory=set)  # bind mounts: built lazily, only when needed

    def say(self, msg: str) -> None:
        if not self.quiet:
            print(msg)


def _recover_orphan_backup(dest: Path) -> None:
    """If an interrupted update left the user's only copy in ``dest.bak`` with dest gone, move it
    back so the skill isn't misread as user-deleted."""
    orphan = dest.with_suffix(".bak")
    if orphan.exists() and not dest.exists():
        try:
            _move_dir(orphan, dest)
            logger.info("Recovered orphaned skill backup: %s", orphan)
        except OSError:
            logger.warning("Could not recover orphaned skill backup %s", orphan, exc_info=True)


def _defer_to_external(st: _SyncState, skill_name: str, dest: Path, bundled_hash: str) -> None:
    """An external_dirs source provides this skill; a local copy would be a name collision the
    loader refuses. Defer for ALL manifest states; remove a stale local shadow from an earlier
    sync only when byte-identical (a user's own skill differs)."""
    st.shadowed_by_external.append(skill_name)
    st.skipped += 1
    st.say(f"  ⇢ {skill_name} (deferred to external_dirs, not written to local tree)")
    if dest.exists() and _dir_hash(dest) == bundled_hash:
        _rmtree_writable(dest)
        st.say(f"  ✓ removed stale shadow of {skill_name}")
        st.manifest.pop(skill_name, None)


def _install_new_skill(st: _SyncState, skill_name: str, skill_src: Path, dest: Path, bundled_hash: str) -> None:
    """Handle a skill never offered before (not in manifest)."""
    try:
        if dest.exists():
            # Never overwrite a same-named user skill. Baseline the manifest only when
            # byte-identical: a differing copy's bundled_hash reads as "user-modified" forever.
            st.skipped += 1
            if _dir_hash(dest) == bundled_hash:
                st.manifest[skill_name] = bundled_hash
            else:
                st.say(
                    f"  ⚠ {skill_name}: bundled version shipped but you already have a local skill "
                    f"by this name — yours was kept. Run `hermes skills reset {skill_name}` to "
                    f"replace it with the bundled version.")
        else:
            _copy_dir(skill_src, dest)
            st.copied.append(skill_name)
            st.manifest[skill_name] = bundled_hash
            st.say(f"  + {skill_name}")
    except OSError as e:
        st.say(f"  ! Failed to copy {skill_name}: {e}")  # not in manifest — next sync retries


def _replace_skill_dir(skill_src: Path, dest: Path) -> None:
    """Replace ``dest`` with a fresh copy of ``skill_src`` via a .bak sibling; restore on failure."""
    backup = dest.with_suffix(".bak")
    if backup.exists():  # a stale .bak would make shutil.move() nest dest INSIDE it
        _rmtree_writable(backup)
    shutil.move(str(dest), str(backup))
    try:
        shutil.copytree(skill_src, dest, ignore=_ignore_runtime_cache)
    except OSError:
        if backup.exists():  # clear a partially-written dest so it can't shadow/block the restore
            if dest.exists():
                try:
                    _rmtree_writable(dest)
                except OSError:
                    logger.warning("Could not clear partial copy %s during restore", dest,
                                   exc_info=True)
            if not dest.exists():
                shutil.move(str(backup), str(dest))
        raise
    try:
        _rmtree_writable(backup)
    except OSError:
        logger.debug("Could not remove backup %s", backup, exc_info=True)


def _update_existing_skill(st: _SyncState, skill_name: str, skill_src: Path, dest: Path, bundled_hash: str) -> None:
    """Handle a skill that is in the manifest AND on disk."""
    origin_hash = st.manifest.get(skill_name, "")
    if origin_hash and bundled_hash == origin_hash:  # bundled unchanged: skip without hashing the user copy
        st.skipped += 1
        return
    user_hash = _dir_hash(dest)
    if not origin_hash:  # v1 migration: baseline from user's copy (can't tell edit from upstream)
        st.manifest[skill_name] = user_hash
        st.skipped += 1
        return
    if not _matches_origin_hash(dest, origin_hash, user_hash):
        st.user_modified.append(skill_name)
        st.user_modified_paths[skill_name] = (dest, skill_src)
        if user_hash == bundled_hash:
            # The copy IS the version shipped now: only the manifest's origin row is stale. Saying
            # "user-modified" here is a claim about the user that the evidence does not support
            # (t_eb487a72: 20 of the 30 flagged names in Morten's home were exactly this).
            st.say(f"  ~ {skill_name} (copy is byte-identical to the version shipped now; the "
                   f"manifest's origin row is an older revision — skipping)")
        else:
            st.say(f"  ~ {skill_name} (copy differs from the version shipped now; skipping — "
                   f"`hermes skills list-modified` says which state it is in)")
        return
    # bundled changed and the user copy is pristine -> update
    try:
        _replace_skill_dir(skill_src, dest)
    except OSError as e:
        st.say(f"  ! Failed to update {skill_name}: {e}")
        return
    st.manifest[skill_name] = bundled_hash
    st.updated.append(skill_name)
    st.say(f"  ↑ {skill_name} (updated)")


def _seed_category_descriptions(bundled_dir: Path, only_dirs: Optional[Set[Path]]) -> None:
    """Copy category DESCRIPTION.md files not already present; ``only_dirs`` restricts
    seeding to the essential skills' categories on opted-out profiles."""
    for desc_md in bundled_dir.rglob("DESCRIPTION.md"):
        dest_desc = _skills_dir() / desc_md.relative_to(bundled_dir)
        if (only_dirs is not None and dest_desc.parent not in only_dirs) or dest_desc.exists():
            continue
        try:
            dest_desc.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(desc_md, dest_desc)
        except OSError as e:
            logger.debug("Could not copy %s: %s", desc_md, e)


def _user_modified_reasons(st: "_SyncState") -> Dict[str, str]:
    """``{skill_name: state}`` for the copies this run skipped, from ONE bounded history read.

    Only runs when something was skipped, so a clean sync pays nothing for it. The states are
    what ``explain_flagged_copy()`` can *prove*; where it cannot prove, the answer is "unproven"
    rather than the flattering one (t_eb487a72).
    """
    if not st.user_modified:
        return {}
    history = _upstream_blob_index([src for _, src in st.user_modified_paths.values()])
    reasons = {}
    for name in st.user_modified:
        dest, src = st.user_modified_paths[name]
        reasons[name] = explain_flagged_copy(dest, src, history=history)["state"]
    return reasons


def _user_modified_breakdown(reasons: Dict[str, str]) -> str:
    """One line naming the states the skipped copies are actually in (never a bare 'user-modified')."""
    order = [COPY_MATCHES_STOCK, COPY_BEHIND_UPSTREAM, COPY_LOCALLY_EDITED, COPY_UNPROVEN]
    labels = {
        COPY_MATCHES_STOCK: "byte-identical to the shipped version (stale manifest row)",
        COPY_BEHIND_UPSTREAM: "behind upstream",
        COPY_LOCALLY_EDITED: "hold local content upstream never shipped",
        COPY_UNPROVEN: "cannot be told apart (no upstream history here)",
    }
    parts = [f"{sum(1 for s in reasons.values() if s == state)} {labels[state]}"
             for state in order if any(s == state for s in reasons.values())]
    return (f"  ~ {len(reasons)} bundled skill(s) not tracking upstream: " + "; ".join(parts)
            + "\n    → per-name state: hermes skills list-modified")


def sync_skills(quiet: bool = False) -> dict:
    """Sync bundled skills into ~/.hermes/skills/ using the manifest; returns the per-category
    result dict. Opted-out profiles seed ONLY ESSENTIAL_SKILLS (the system prompt always
    points at ``hermes-agent``)."""
    essential_only = (_hermes_home() / NO_BUNDLED_SKILLS_MARKER).exists()
    if essential_only and not quiet:
        print("  (profile opted out of bundled skills via .no-bundled-skills — seeding essential skills only)")
    bundled_dir = _get_bundled_dir()
    if not bundled_dir.exists():
        return {"copied": [], "updated": [], "skipped": 0, "user_modified": [], "cleaned": [],
                "suppressed": [], "total_bundled": 0, "optional_provenance_backfilled": [],
                "user_modified_reasons": {}, "manifest_error": "", "unrecorded": []}
    _skills_dir().mkdir(parents=True, exist_ok=True)
    bundled_skills = _discover_bundled_skills(bundled_dir)
    if essential_only:
        bundled_skills = [(name, src) for name, src in bundled_skills if name in ESSENTIAL_SKILLS]
    suppressed = _read_suppressed_names()
    external_index = _build_external_skill_index()
    try:
        existing_manifest = _read_manifest()
    except ManifestReadError as e:
        # Refuse the whole sync: every bundled skill would look "new" against an empty manifest,
        # and the run would silently re-baseline the entire set — the exact damage the read error
        # exists to prevent. Say it out loud and change nothing on disk (t_eb487a72).
        logger.error("Refusing to sync bundled skills: %s", e)
        if not quiet:
            print(f"  ! {e}\n  ! No bundled skill was touched by this run.")
        return {"copied": [], "updated": [], "skipped": 0, "user_modified": [], "cleaned": [],
                "suppressed": [], "total_bundled": len(bundled_skills),
                "optional_provenance_backfilled": [], "user_modified_reasons": {},
                "manifest_error": str(e), "unrecorded": [], "relocated": []}
    st = _SyncState(manifest=existing_manifest, quiet=quiet)

    for skill_name, skill_src in bundled_skills:
        # Curator-pruned built-ins must not resurrect on every update; essentials are exempt.
        if skill_name in suppressed and skill_name not in ESSENTIAL_SKILLS:
            st.suppressed.append(skill_name)
            continue
        dest = _compute_relative_dest(skill_src, bundled_dir)
        bundled_hash = _dir_hash(skill_src)
        # Recoveries run BEFORE classification so a missing dest isn't misread as user-deleted.
        _recover_orphan_backup(dest)
        if not dest.exists() and skill_name in st.manifest and _recover_renamed_skill(st, skill_name, dest):
            st.relocated.append(skill_name)
        if skill_name in external_index:
            _defer_to_external(st, skill_name, dest, bundled_hash)
        elif skill_name not in st.manifest:
            _install_new_skill(st, skill_name, skill_src, dest, bundled_hash)
        elif dest.exists():
            _update_existing_skill(st, skill_name, skill_src, dest, bundled_hash)
        else:
            st.skipped += 1  # in manifest but not on disk — user deleted it
    # Clean manifest entries for skills removed upstream. Skipped when opted out: bundled_skills
    # is only the essential set there, so cleaning would drop tracking for everything else.
    cleaned = [] if essential_only else sorted(set(st.manifest) - {name for name, _ in bundled_skills})
    for name in cleaned:
        del st.manifest[name]
    _seed_category_descriptions(
        bundled_dir,
        {_compute_relative_dest(src, bundled_dir).parent for _, src in bundled_skills} if essential_only else None)
    reasons = _user_modified_reasons(st)
    manifest_error = ""
    unrecorded: List[str] = []
    try:
        _write_manifest(st.manifest)
    except ManifestWriteError as e:
        # The copies on disk DID change, but their origin rows are not recorded — which is exactly
        # the state that made `hermes update` report "↑ 27 updated" while the next phase of the
        # same run read all 27 as user-modified. Do not repeat it: report the names, not a success.
        manifest_error = str(e)
        unrecorded = sorted(set(st.copied) | set(st.updated))
        st.updated = []
        logger.error("Bundled-skill sync changed %d skill(s) on disk but the manifest write failed, "
                     "so none of their origin rows are recorded: %s", len(unrecorded), e)
        if not quiet:
            print(f"  ! manifest write FAILED — {len(unrecorded)} skill(s) were written to disk but "
                  f"not recorded ({e}); they will read as user-modified on the next run.")
    if reasons and not quiet:
        print(_user_modified_breakdown(reasons))
    return {
        "copied": st.copied, "updated": st.updated, "skipped": st.skipped, "user_modified": st.user_modified,
        "user_modified_reasons": reasons,
        "manifest_error": manifest_error, "unrecorded": unrecorded,
        "cleaned": cleaned, "suppressed": st.suppressed, "relocated": st.relocated,
        "total_bundled": len(bundled_skills),
        "optional_provenance_backfilled": _backfill_optional_provenance(quiet=quiet),
        "shadowed_by_external": st.shadowed_by_external,
        "skipped_opt_out": essential_only}  # lets callers report "opted out", not a normal sync


def _rmtree_writable(path: Path) -> None:
    """rmtree that first makes read-only entries writable (Nix/deb/rpm keep r-x dirs; unlinking
    a child needs a writable parent, so chmod both). Scope guard: refuses anything not a STRICT
    child of the active skills root (bad join / missing HERMES_HOME / malicious manifest entry).

    Handles immutable package sources (Nix store, deb/rpm installs) that preserve read-only permissions on
    copied files *and* directories (``r-xr-xr-x``). Removing a child requires write permission on its parent
    directory, so the retry handler makes the failing path **and its parent** writable before re-attempting.
    See #34860, #34972.
    """
    target = Path(path).resolve()
    skills_root = _skills_dir().resolve()
    if skills_root not in target.parents:
        raise ValueError(f"refusing to rmtree {target!r}: not strictly under {skills_root!r} (scope guard — see #48200)")

    def _on_error(func, fpath, exc_info):
        for p in (os.path.dirname(fpath), fpath):
            with suppress(OSError):
                os.chmod(p, stat.S_IRWXU)
        func(fpath)
    shutil.rmtree(path, onerror=_on_error)


if __name__ == "__main__":
    print("Syncing bundled skills into ~/.hermes/skills/ ...")
    result = sync_skills(quiet=False)
    parts = [f"{len(result['copied'])} new", f"{len(result['updated'])} updated", f"{result['skipped']} unchanged"]
    if names := result["user_modified"]:
        shown = ", ".join(names[:5]) + (f", +{len(names) - 5} more" if len(names) > 5 else "")
        parts.append(f"{len(names)} not tracking upstream (kept): {shown}")
    if result["cleaned"]:
        parts.append(f"{len(result['cleaned'])} cleaned from manifest")
    if backfilled := result.get("optional_provenance_backfilled"):
        parts.append(f"{len(backfilled)} official optional backfilled")
    if result["manifest_error"]:
        parts.append(f"MANIFEST WRITE FAILED ({len(result['unrecorded'])} unrecorded)")
    print(f"\nDone: {', '.join(parts)}. {result['total_bundled']} total bundled.")


# ---- BEGIN PLUGIN-COMPAT (revert-scheduled; see COMPAT_MANIFEST.md) ----
# Names external plugins imported from this module before the Sep 2026 decomposition.
# Internal code MUST NOT use these (scripts/check_compat_pointers.py fails CI if it does).
# The whole block is removed by reverting the commit that added it.
from pathlib import PurePosixPath  # noqa: F401,E402
from datetime import datetime  # noqa: F401,E402
import json  # noqa: F401,E402
from datetime import timezone  # noqa: F401,E402

def is_bundled_skills_opt_out() -> bool:
    """Return True if the active profile carries the opt-out marker."""
    return (_hermes_home() / NO_BUNDLED_SKILLS_MARKER).exists()


_PLUGIN_COMPAT_LAZY = {
    'atomic_replace': ('utils', 'atomic_replace'),
    'diff_bundled_skill': ('tools.skills_sync_bundled_ops', 'diff_bundled_skill'),
    'list_user_modified_bundled_skills': ('tools.skills_sync_bundled_ops', 'list_user_modified_bundled_skills'),
    'remove_pristine_bundled_skills': ('tools.skills_sync_bundled_ops', 'remove_pristine_bundled_skills'),
    'reset_bundled_skill': ('tools.skills_sync_bundled_ops', 'reset_bundled_skill'),
    'restore_official_optional_skill': ('tools.skills_sync_optional', 'restore_official_optional_skill'),
    'set_bundled_skills_opt_out': ('tools.skills_sync_bundled_ops', 'set_bundled_skills_opt_out'),
}


def __getattr__(name):  # PEP 562 — lazy so no import cycles
    target = _PLUGIN_COMPAT_LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    from hermes_cli.plugin_compat import warn_once
    warn_once(__name__, name, *target)
    return getattr(importlib.import_module(target[0]), target[1])
# ---- END PLUGIN-COMPAT ----
