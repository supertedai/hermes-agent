"""faber_goal_state.py — durable per-goal chain state for the governed workflow (BL-4006).

WHY THIS EXISTS
---------------
The 13-step workflow spans more than one job, but nothing carried state between
steps.  Measured on .15 before this module existed:

  * ``observe-last.json``   — a snapshot, overwritten every tick.
  * ``activation-todo.log`` — 338 append-only lines, ONE distinct value.

Both are *reports*.  Neither is a state machine, so step N+1 had no way to learn
that step N happened, and a goal refused for the same reason 338 times looked
exactly like a goal refused once.  That is why the long-lived orchestrator kept
being proposed: not because the chain needs a daemon, but because it needs a
memory.  With a durable record, 480 s stops being a chain budget and becomes a
per-step budget, and the orchestrator drops from prerequisite to optimization.

THE CONTRACT — load-bearing, do not weaken
------------------------------------------
**This module is a JOURNAL, never EVIDENCE.**  ``PreflightGate`` must never read
it to decide anything.  The distinction is the whole point:

  * a journal records *what the system observed about itself*;
  * evidence is *what authorises work to proceed*.

If the gate ever consults this file, the producer gains the ability to write a
record that opens a gate — precisely the defect reviewer BLOCKed in BL-3673
(``cab10c5f9``: "jeg skrev en post for aa faa en gate til aa slippe meg gjennom").
Evidence must come from an authority the producer cannot write.  This file is
written by the producer, so it can never be that authority.

Nothing here grants, unblocks, or upgrades anything.  It counts and remembers.

**How strongly is that enforced?  Honestly: documented, tripwired and
import-guarded — not proven.**  The name blacklist in the test suite catches
``allow``/``passes`` and friends, but not ``is_actionable`` or ``can_proceed``.
The real risk is a *consumer* reading ``goal-state.json`` and deriving a verdict
from it, which no test here can prevent — the journal is a JSON file in the same
directory the gate reads.  A dynamic ``importlib.import_module`` would also slip
past.  The one mechanically strong guard is the import-direction test: the
gate's modules must never import this one, and it is enforced statically by
``test_gate_modules_do_not_import_the_journal`` in
``tests/test_faber_goal_state.py``.  It lives there rather than in the gate's own
suite because ``tests/test_code_workflow.py`` is owned by another stream; move it
when that lease clears.

WHAT IT BUYS
------------
``unchanged_ticks`` and ``last_change_at`` turn "338 identical log lines" into a
single checkable fact: *this goal has been refused for the same reason N times
since T*.  A gate whose PASS condition has never been reached becomes visible as
a number instead of as a wall of text nobody reads.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

#: Bounded history per goal.  Kept small on purpose: the *summary* fields carry
#: the long-run signal, so history only needs enough depth to see recent churn.
#: Truncation is never silent — ``dropped_history_total`` is persisted per entry
#: so the cumulative loss stays recoverable from the journal itself.
HISTORY_LIMIT = 20

SCHEMA_VERSION = 1

DEFAULT_PATH = Path(
    os.environ.get("HERMES_HOME", str(Path.home() / ".hermes-gui"))
) / "faber" / "goal-state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def reason_digest(reasons: Iterable[str]) -> str:
    r"""Stable digest of a refusal-reason SET.

    Order-insensitive and whitespace-normalised, because the same refusal
    re-emitted in a different order is the same refusal.  BL-4000's lesson
    applies directly: a reproposal can be identical in payload and
    unrecognisable in prose, so compare payload, never prose.

    ``\x1f`` separates rather than a space: with a space, ``["a b"]`` and
    ``["a", "b"]`` would collide.

    KNOWN BLIND SPOT — measured, not theoretical.  This digests the gate's
    rendered *message*, so it cannot see a change the message discards.  The
    live instance is BL-4003 punkt 1: ``git_is_clean("")`` (no repo configured)
    and ``git_is_clean(<dirty tree>)`` both render the identical string
    ``git target is dirty or has unowned changes``.  When punkt 1 lands, git
    goes from *never measured* to *measured and genuinely dirty* — a material
    change in the world — and this digest reports UNCHANGED.  Pass a
    ``fingerprint`` to :func:`record` to close it wherever the structured value
    is actually available to the caller.
    """
    norm = sorted(" ".join(str(r).split()) for r in reasons)
    h = hashlib.sha256("\x1f".join(norm).encode("utf-8")).hexdigest()
    return f"sha256:{h[:16]}"


def _fingerprint_key(fingerprint: dict[str, Any] | None) -> str:
    """Canonical form of the structured fingerprint, for equality comparison."""
    if not fingerprint:
        return ""
    return json.dumps(fingerprint, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class RecordOutcome:
    """What :func:`record` did — returned so callers can report honestly."""

    goal_id: str
    seq: int
    changed: bool
    unchanged_ticks: int
    dropped_history: int
    #: True when this tick only backfilled a field the schema gained, with no
    #: change in the world.  Reported separately from ``changed`` because a
    #: SCHEMA event wearing a DOMAIN event's costume is the defect class this
    #: whole module exists to surface.
    migrated: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "seq": self.seq,
            "changed": self.changed,
            "migrated": self.migrated,
            "unchanged_ticks": self.unchanged_ticks,
            "dropped_history": self.dropped_history,
        }


def load(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Read the journal.  A missing file is an EMPTY journal, not an error.

    Absence is reported as absence: callers get ``goals: {}`` and can say "no
    state recorded" rather than inferring something green from a default.

    A file that exists but cannot be read is NOT the same thing, and is marked
    ``unreadable``/``malformed`` so a caller can refuse to overwrite it.  See
    :func:`record_all`, which quarantines rather than resetting.
    """
    p = Path(path or DEFAULT_PATH)
    if not p.exists():
        return {"version": SCHEMA_VERSION, "goals": {}}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": SCHEMA_VERSION, "goals": {}, "unreadable": str(p)}
    if not isinstance(doc, dict) or not isinstance(doc.get("goals"), dict):
        return {"version": SCHEMA_VERSION, "goals": {}, "malformed": str(p)}
    doc.setdefault("version", SCHEMA_VERSION)
    return doc


def _save(doc: dict[str, Any], path: str | os.PathLike[str]) -> Path:
    """Atomic write — tmp + fsync + rename in the same directory.

    A half-written journal would be indistinguishable from a corrupt one, and
    this file is read by the next tick.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".goal-state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return p


def record(
    goal_id: str,
    *,
    phase: str,
    outcome: str,
    reasons: Sequence[str] = (),
    fingerprint: dict[str, Any] | None = None,
    doc: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], RecordOutcome]:
    """Record one observation of one goal.  Returns ``(doc, outcome)``.

    ``seq`` is **monotonic within a journal generation**.  A journal that cannot
    be read is quarantined rather than silently restarted — see
    :func:`record_all`.  That qualifier matters: an earlier version of this
    docstring said "monotonic by construction" unqualified, while a corrupt load
    reset ``seq`` to 1 and the tick reported it as a normal first run.

    A phase that goes BACKWARDS is a legitimate event (a chain can be restarted)
    and is recorded as such — never a silent overwrite, because a silently
    rewound chain is exactly the failure this module exists to make visible.

    ``last_change_at`` moves only when the observation actually changes.  That
    is what separates "blocked once" from "blocked identically 338 times".
    """
    if not str(goal_id).strip():
        raise ValueError("goal_id must be non-empty")
    doc = doc if doc is not None else load()
    goals = doc.setdefault("goals", {})
    now = _now()
    digest = reason_digest(reasons)
    fp_key = _fingerprint_key(fingerprint)

    prev = goals.get(goal_id)
    if prev is None:
        goals[goal_id] = {
            "seq": 1,
            "phase": phase,
            "outcome": outcome,
            "reason_digest": digest,
            "reasons": list(reasons),
            "fingerprint": fingerprint or {},
            "first_seen_at": now,
            "last_change_at": now,
            "last_observed_at": now,
            "unchanged_ticks": 0,
            "dropped_history_total": 0,
            "history": [
                {"seq": 1, "at": now, "phase": phase, "outcome": outcome, "digest": digest}
            ],
        }
        return doc, RecordOutcome(goal_id, 1, True, 0, 0)

    # MIGRATION, and it is load-bearing.  A pre-BL-4006 entry has no
    # ``fingerprint`` key at all.  Treating that absence as "different" would
    # reset ``unchanged_ticks`` to 0 and move ``last_change_at`` to now — i.e.
    # a goal refused identically since 1 July would report a fresh change on
    # the first wired run, and the module's headline sentence ("refused for the
    # same reason N times since T") would be FALSE for every goal at exactly
    # the moment it starts being trusted.
    #
    # A SCHEMA change (we now record more) is not a WORLD change (the goal's
    # situation moved).  Absent-previous means "no signal", never "different".
    # The streak is the asset; a schema upgrade must not spend it.
    prev_fp = prev.get("fingerprint")
    fp_comparable = prev_fp is not None
    same_apart_from_fingerprint = (
        prev.get("reason_digest") == digest
        and prev.get("phase") == phase
        and prev.get("outcome") == outcome
    )
    same = same_apart_from_fingerprint and (
        not fp_comparable or _fingerprint_key(prev_fp) == fp_key
    )
    migrated = (not fp_comparable) and same_apart_from_fingerprint

    seq = int(prev.get("seq", 0)) + 1
    prev["seq"] = seq
    prev["phase"] = phase
    prev["outcome"] = outcome
    prev["reason_digest"] = digest
    prev["reasons"] = list(reasons)
    prev["fingerprint"] = fingerprint or {}
    prev["last_observed_at"] = now
    prev.setdefault("first_seen_at", now)
    prev.setdefault("dropped_history_total", 0)

    dropped = 0
    if same:
        prev["unchanged_ticks"] = int(prev.get("unchanged_ticks", 0)) + 1
        # Deliberately NOT appended to history: an unchanged observation is
        # counted, not re-listed.  Re-listing is how activation-todo.log ended
        # up with 338 lines and one fact.
    else:
        prev["unchanged_ticks"] = 0
        prev["last_change_at"] = now
        hist = list(prev.get("history") or [])
        hist.append(
            {"seq": seq, "at": now, "phase": phase, "outcome": outcome, "digest": digest}
        )
        if len(hist) > HISTORY_LIMIT:
            dropped = len(hist) - HISTORY_LIMIT
            hist = hist[-HISTORY_LIMIT:]
            prev["dropped_history_total"] = int(prev["dropped_history_total"]) + dropped
        prev["history"] = hist

    return doc, RecordOutcome(
        goal_id, seq, not same, int(prev["unchanged_ticks"]), dropped, migrated
    )


def summarise(doc: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aggregate the journal into the numbers a health check can act on.

    ``never_changed`` is the one that matters: goals whose recorded outcome has
    never differed from the first observation.  A gate whose PASS condition has
    never been reached shows up here as a count, which is what makes it
    actionable instead of merely true.
    """
    doc = doc if doc is not None else load()
    goals = doc.get("goals") or {}
    rows = []
    for gid, e in sorted(goals.items()):
        retained = len(e.get("history") or [])
        dropped = int(e.get("dropped_history_total", 0) or 0)
        rows.append(
            {
                "goal_id": gid,
                "phase": e.get("phase"),
                "outcome": e.get("outcome"),
                "seq": e.get("seq"),
                "unchanged_ticks": e.get("unchanged_ticks", 0),
                "first_seen_at": e.get("first_seen_at"),
                "last_change_at": e.get("last_change_at"),
                # Named for what they ARE: an earlier version called the capped
                # retained count "transitions" — a silent cap presented as a
                # total.
                "history_retained": retained,
                "history_dropped": dropped,
                "history_total": retained + dropped,
                # BL-4029 L9: the DISTINCT outcomes ever recorded for this goal
                # (current + retained history). A fact, not a judgement -- the
                # journal still refuses to say whether any of them is good.
                # Consumers need it because "the goal changed" and "the goal
                # passed" are different questions, and conflating them is how a
                # churning-but-never-passing gate reads as healthy.
                "outcomes_seen": sorted(
                    {str(h.get("outcome")) for h in (e.get("history") or []) if h.get("outcome")}
                    | ({str(e.get("outcome"))} if e.get("outcome") else set())
                ),
            }
        )
    never_changed = [r for r in rows if (r["history_total"] or 0) <= 1 and (r["seq"] or 0) > 1]
    return {
        "artifact": "faber-goal-state-summary-v1",
        "goals": len(rows),
        "never_changed": [r["goal_id"] for r in never_changed],
        "never_changed_count": len(never_changed),
        "max_unchanged_ticks": max((r["unchanged_ticks"] or 0 for r in rows), default=0),
        "source_observed_at": doc.get("source_observed_at"),
        "rows": rows,
        "note": (
            "JOURNAL, not evidence — nothing here authorises work. "
            "never_changed lists goals whose recorded outcome has never differed "
            "since first observation."
        ),
    }


def record_all(
    observations: Iterable[dict[str, Any]],
    *,
    path: str | os.PathLike[str] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Record a whole observe-tick under an exclusive lock.  Writes once.

    Three refusals, all deliberate:

    * an UNREADABLE journal is quarantined and NOT overwritten — overwriting
      would convert a recoverable corruption into a silent history reset, the
      exact defect class this module exists to surface;
    * an observation with no ``goal_id`` is counted, not silently dropped;
    * a source snapshot already recorded is a NO-OP, because re-recording an
      unchanged ``observe-last.json`` would inflate ``unchanged_ticks`` with
      ticks that never happened — corrupting the one number this module exists
      to make trustworthy.
    """
    target = Path(path or DEFAULT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")

    # "a+" rather than "w": matches code_workflow.py's lock idiom and avoids
    # truncating the lock file on every acquire. Contents are never read.
    with open(lock_path, "a+", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        # Re-read INSIDE the lock: another tick may have written between our
        # open() and our acquire().
        doc = load(target)

        damaged = doc.get("unreadable") or doc.get("malformed")
        if damaged:
            stamp = _now().replace(":", "").replace("-", "")
            quarantine = target.with_name(f"{target.name}.corrupt-{stamp}")
            try:
                os.replace(target, quarantine)
            except OSError as exc:
                return {
                    "artifact": "faber-goal-state-tick-v1",
                    "status": "BLOCK",
                    "reason": f"journal unreadable and could not be quarantined: {exc}",
                    "recorded": 0,
                }
            return {
                "artifact": "faber-goal-state-tick-v1",
                "status": "BLOCK",
                "reason": "journal unreadable; preserved and not overwritten",
                "quarantined_to": str(quarantine),
                "recorded": 0,
            }

        if observed_at and doc.get("source_observed_at") == observed_at:
            return {
                "artifact": "faber-goal-state-tick-v1",
                "status": "SKIPPED",
                "reason": "source snapshot unchanged — no tick to record",
                "source_observed_at": observed_at,
                "recorded": 0,
            }

        outcomes = []
        skipped_without_goal_id = 0
        for obs in observations:
            gid = str(obs.get("goal_id") or "").strip()
            if not gid:
                skipped_without_goal_id += 1
                continue
            doc, out = record(
                gid,
                phase=str(obs.get("stopped_by") or obs.get("phase") or "unknown"),
                outcome=str(obs.get("preflight") or obs.get("outcome") or "unknown"),
                reasons=list(obs.get("reasons") or []),
                # Structured fields that survive the gate's prose rendering.
                # This does NOT close the git blind spot documented in
                # reason_digest — that value never reaches this payload.
                fingerprint={
                    k: obs.get(k)
                    for k in ("gate", "state", "bl_ref")
                    if obs.get(k) is not None
                },
                doc=doc,
            )
            outcomes.append(out)

        if observed_at:
            doc["source_observed_at"] = observed_at
        _save(doc, target)

    return {
        "artifact": "faber-goal-state-tick-v1",
        "status": "EXECUTED",
        "path": str(target),
        "recorded": len(outcomes),
        "changed": [o.goal_id for o in outcomes if o.changed],
        "changed_count": sum(1 for o in outcomes if o.changed),
        # Schema backfills are NOT world changes. Reported apart so a migration
        # can never be read as seven goals suddenly moving.
        "migrated_count": sum(1 for o in outcomes if o.migrated),
        "skipped_without_goal_id": skipped_without_goal_id,
        # No silent caps: report per-tick drops; the cumulative total lives on
        # each entry as dropped_history_total.
        "dropped_history_entries": sum(o.dropped_history for o in outcomes),
        "source_observed_at": observed_at,
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Durable per-goal chain state for the governed Faber workflow. "
        "A journal — it never authorises anything."
    )
    ap.add_argument("--path", default=None, help=f"journal path (default: {DEFAULT_PATH})")
    ap.add_argument(
        "--from-observe",
        default=None,
        metavar="OBSERVE_JSON",
        help="record a tick from an observe-last.json produced by faber_observe",
    )
    ap.add_argument("--summary", action="store_true", help="print the aggregate summary")
    args = ap.parse_args(argv)

    target = Path(args.path or DEFAULT_PATH)

    def block(reason: str) -> int:
        print(
            json.dumps({"status": "BLOCK", "reason": reason}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    if args.from_observe:
        src = Path(args.from_observe)
        if not src.exists():
            return block(f"missing {src}")
        try:
            payload = json.loads(src.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return block(f"unreadable {src}: {exc}")
        obs = payload.get("observations")
        if not isinstance(obs, list):
            return block("no 'observations' list")
        res = record_all(obs, path=target, observed_at=payload.get("observed_at"))
        blob = json.dumps(res, ensure_ascii=False, sort_keys=True)
        print(blob)
        if res.get("status") == "BLOCK":
            # A quarantined journal is a real failure, not a quiet note. It also
            # goes to STDERR because the cron caller sends stdout to /dev/null —
            # the journal itself is the record, so routine ticks need no log.
            # Without this the loudest failure would be the most invisible one.
            print(blob, file=sys.stderr)
            return 2
        return 0

    if args.summary:
        print(json.dumps(summarise(load(target)), ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
