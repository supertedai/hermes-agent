# BL-4029 L8: THIS is the authoritative copy of code_workflow.py --
# the observe cron runs from this tree. Three other copies exist on .15
# (mwp-uosh-automation-01, hermes-mwp-cleanup, .hermes-gui/faber/sandbox);
# each carries a banner pointing here. Measured 2026-08-10: they have
# diverged (1020 / 672 / 662 / 662 lines).
"""Governed Code/Faber workflow gates.

This module is deliberately side-effect free. It turns the Code workflow rails
into typed, fail-closed decisions that can be fed by Hermes/Symbiose/CAD/ADR/BL
adapters without duplicating their storage.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class PreflightStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class GoalState(str, Enum):
    CANDIDATE = "candidate"
    PROPOSED = "proposed"
    APPROVED = "approved"
    PLANNED = "planned"
    BUILDING = "building"
    VERIFIED = "verified"
    LANDED = "landed"
    MEASURED = "measured"
    LEARNED = "learned"
    BLOCKED = "blocked"


class ReviewVerdict(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class FailureClass(str, Enum):
    """Machine-readable reason class for blocked/retryable workflow steps."""

    TEST = "TEST"
    ARCHITECTURE = "ARCHITECTURE"
    EVIDENCE = "EVIDENCE"
    CI = "CI"
    SECURITY = "SECURITY"
    LEASE = "LEASE"
    RUNTIME = "RUNTIME"
    REVIEW = "REVIEW"
    OWNER_GATE = "OWNER_GATE"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class ScopeBudget:
    """Configurable blast-radius limits evaluated before a build."""

    max_files: int = 10
    max_changed_lines: int = 500
    max_deleted_lines: int = 250
    max_new_dependencies: int = 0

    def evaluate(
        self,
        *,
        changed_files: int,
        changed_lines: int,
        deleted_lines: int = 0,
        new_dependencies: int = 0,
    ) -> tuple[bool, tuple[str, ...]]:
        violations: list[str] = []
        if changed_files > self.max_files:
            violations.append(f"files>{self.max_files}: {changed_files}")
        if changed_lines > self.max_changed_lines:
            violations.append(f"lines>{self.max_changed_lines}: {changed_lines}")
        if deleted_lines > self.max_deleted_lines:
            violations.append(f"deletions>{self.max_deleted_lines}: {deleted_lines}")
        if new_dependencies > self.max_new_dependencies:
            violations.append(f"dependencies>{self.max_new_dependencies}: {new_dependencies}")
        return not violations, tuple(violations)


class SecretPolicy:
    """Negative gate for credential-like material before evidence is persisted.

    BL-4029 -- REWRITTEN. The inherited version was structurally unable to fire
    where it was used. Measured:

        CAUGHT   api_key=sk-abc123
        MISSED   {"api_key": "sk-abc123"}
        MISSED   {"password": "hunter2"}
        MISSED   {"token": "ghp_realtoken"}

    Cause: the key pattern required ``keyword`` followed by optional whitespace
    then ``:`` or ``=``. In JSON a closing quote sits between them, so it never
    matched -- and the ONLY call site serialises to JSON *first*, then applies
    the regex. The gate ran, returned clean, and could not fire on anything but
    a bare PEM header.

    **That is worse than no gate, because it gets cited as one.** A control
    that cannot fail is indistinguishable from a control that never triggers,
    which is the defect class this whole BL is about.

    Two changes: the key patterns tolerate a quote before the delimiter, and
    :meth:`assert_safe_payload` walks the structure BEFORE serialisation, so
    the check no longer depends on the shape of the encoding.
    """

    _PATTERNS = (
        # keyword, optional closing quote, then : or = -- covers bare, JSON and YAML
        re.compile(r"(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd"
                   r"|private[_-]?key|client[_-]?secret|token)[\"']?\s*[:=]\s*[\"']?[^\s,}\"']+"),
        re.compile(r"(?i)authorization\s*:\s*(bearer|basic)\s+\S+"),
        # bare provider-shaped tokens, which carry no keyword at all
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
        re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    )

    #: Keys whose VALUE is credential-like regardless of what the value looks
    #: like. Checked structurally, so a short or unusual secret is still caught.
    _SENSITIVE_KEYS = frozenset({
        "api_key", "apikey", "access_token", "auth_token", "token", "secret",
        "client_secret", "password", "passwd", "private_key", "authorization",
    })

    @classmethod
    def violations(cls, text: str) -> tuple[str, ...]:
        if not isinstance(text, str):
            return ()
        return tuple(p.pattern for p in cls._PATTERNS if p.search(text))

    @classmethod
    def structural_violations(cls, payload: object, _path: str = "") -> tuple[str, ...]:
        """Walk a mapping/sequence and flag sensitive KEYS with non-empty values.

        Done before serialisation on purpose: a check that depends on the
        encoding is a check that a different encoder silently disables.
        """
        found: list[str] = []
        if isinstance(payload, Mapping):
            for k, v in payload.items():
                key = str(k).strip().lower().replace("-", "_")
                here = f"{_path}.{k}" if _path else str(k)
                if key in cls._SENSITIVE_KEYS and str(v).strip():
                    found.append(f"sensitive key: {here}")
                found.extend(cls.structural_violations(v, here))
        elif isinstance(payload, (list, tuple)):
            for i, v in enumerate(payload):
                found.extend(cls.structural_violations(v, f"{_path}[{i}]"))
        elif isinstance(payload, str):
            found.extend(f"{_path}: {p}" for p in cls.violations(payload))
        return tuple(found)

    @classmethod
    def assert_safe(cls, text: str) -> None:
        if cls.violations(text):
            raise PermissionError("secrets policy BLOCK: credential-like material detected")

    @classmethod
    def assert_safe_payload(cls, payload: object) -> None:
        """Preferred entry point: structure first, then the serialised form."""
        hits = cls.structural_violations(payload)
        if hits:
            raise PermissionError(
                "secrets policy BLOCK: credential-like material detected "
                f"({len(hits)} finding(s))")
        cls.assert_safe(json.dumps(payload, ensure_ascii=False, default=str))


class StepJournal:
    """Atomic, durable idempotency journal for workflow side-effect steps."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("step journal must contain an object")
        return {str(k): dict(v) for k, v in payload.items() if isinstance(v, dict)}

    def _write(self, payload: Mapping[str, Mapping[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def get(self, key: str) -> Mapping[str, Any] | None:
        return self._load().get(key)

    def complete(self, key: str, *, result: Mapping[str, Any]) -> Mapping[str, Any]:
        # BL-4029: structure first. The previous call serialised to JSON and then
        # applied a regex that could not match JSON.
        SecretPolicy.assert_safe_payload(result)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The file replacement in _write() prevents partial reads, but it does
        # not protect the read-modify-write sequence. Without this lock two
        # concurrent side-effect workers can each read the same old payload and
        # silently discard the other's completed step.
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                payload = self._load()
                existing = payload.get(key)
                if existing is not None:
                    return {**existing, "status": "ALREADY_DONE"}
                record = {
                    "status": "DONE",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": dict(result),
                }
                payload[key] = record
                self._write(payload)
                return record
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class ReviewEvidence:
    verdict: ReviewVerdict
    diff_id: str
    reviewer: str = ""


@dataclass(frozen=True)
class PreflightInput:
    """Evidence collected before code changes begin.

    Status values are intentionally strings so adapters can preserve source
    vocabulary (fresh/stale, accepted/proposed, open/blocked, etc.).
    """

    git_clean: bool
    lease_clear: bool
    cad_status: str
    adr_status: str
    bl_status: str
    #: BL-4029 L4: read by NO gate. Brain/Obsidian freshness was deliberately
    #: turned from an entry condition into a closeout assertion (step 13,
    #: DefinitionOfDone) because CLAUDE.md places the Brain node under ETTER.
    #: The field stays for producer compatibility -- do not assume a field on
    #: the gate's input is checked by a gate.
    obsidian_status: str
    source_refs: Mapping[str, str] = field(default_factory=dict)
    #: BL-4029 L4: is the goal's target scope present and executable on THIS
    #: host?  Defaults True so existing callers keep working; an adapter that
    #: knows the answer must set it.  Measured 2026-08-10: 5 of 7 goals carry
    #: AGI scope while the AGI codebase does not exist on .15, so they were
    #: failing at step 8 or later, or being "fixed" by checking AGI out there
    #: -- which ADR-062 V2 forbids.
    scope_executable: bool = True
    scope_note: str = ""


@dataclass(frozen=True)
class PreflightResult:
    status: PreflightStatus
    reasons: tuple[str, ...]
    evidence: PreflightInput


class PreflightGate:
    """Step 4 gate: COLLISION AND SCOPE CONTROL. Not design certification.

    ADR-062 V4 / BL-4029 L4.  Until 2026-08-10 this gate also demanded CAD,
    ADR, BL and Brain evidence, and the result was ``preflight_clear: 0`` of 7
    across 340 consecutive samples -- never once a pass.

    The cause was not a bug.  **It was circular:** the workflow's own step list
    produces those artifacts LATER than step 4.

    =====================  ==========================================
    evidence               produced at
    =====================  ==========================================
    BL actionable          step 5   ``bl_gate``
    CAD / ADR              step 7   ``sol_design_review_pass``
    Brain / Obsidian       step 13  ``postcommit_readback`` (CLAUDE.md
                                    puts the Brain node under ETTER)
    =====================  ==========================================

    Demanding them at step 4 asked the chain for its own output as its input,
    so no sequence of legitimate actions could open the gate.  The falsifier
    -- *is there a sequence of legitimate actions that makes this pass?* -- had
    no answer.  Note what the previous design pressured people into: the only
    way through was to WRITE a status, which is exactly what reviewer BLOCKed
    in BL-3673 (``cab10c5f9``, "jeg skrev en post for aa faa en gate til aa
    slippe meg gjennom").  A gate that can only be passed by fabricating
    evidence is a gate that teaches fabrication.

    **Nothing is deleted.**  Each check moved to the phase that produces its
    input -- see :class:`BlGate` (step 5) and :class:`DesignGate` (step 7).
    One impossible gate became three possible ones.

    What remains here is what step 4 can honestly ask, and all three are
    self-evidencing -- they are true because someone DID something, not
    because someone wrote that they did:

      1. a lease is held on the files the change will touch;
      2. those leased files are clean;
      3. the target scope exists and is executable on this host.

    The harm this actually prevents is the one CLAUDE.md documents
    (``ae832c8a4`` -- sweeping a parallel session's work).  Design quality is
    judged at steps 7 and 10, by roles that can judge it.
    """

    #: Refs that must resolve AT STEP 4.  ``cad``/``adr``/``bl``/``obsidian``
    #: are deliberately absent: requiring a reference to an artifact that does
    #: not exist yet is the circularity above in its smallest form.
    REQUIRED_REFS: tuple[str, ...] = ("git", "lease")

    def evaluate(self, evidence: PreflightInput) -> PreflightResult:
        reasons: list[str] = []
        missing_refs = tuple(r for r in self.REQUIRED_REFS if not evidence.source_refs.get(r))
        if missing_refs:
            reasons.append("missing authoritative source refs: " + ", ".join(missing_refs))
        if not evidence.git_clean:
            reasons.append("git target is dirty or has unowned changes")
        if not evidence.lease_clear:
            reasons.append("target lease is not clear")
        if not evidence.scope_executable:
            detail = evidence.scope_note or "target scope not present on this host"
            reasons.append(f"scope is not executable on this host: {detail}")
        status = PreflightStatus.PASS if not reasons else PreflightStatus.BLOCK
        return PreflightResult(status, tuple(reasons), evidence)


class BlGate:
    """Step 5 gate: is there an ACTIONABLE work item behind the number?

    Split out of :class:`PreflightGate` by BL-4029 L4.  The check itself is
    unchanged and deliberately strict: BL-3673 established that a *reserved*
    number means a number was handed out, not that work exists.  Promoting
    ``reserved`` to ``open`` to get through is writing a record to open a gate.

    It sits at step 5 because step 5 IS ``bl_gate`` -- asking for it at step 4
    was asking the chain for step 5's output one step early.
    """

    ACTIONABLE: frozenset[str] = frozenset({"open", "approved", "in_progress", "reviewed"})

    def evaluate(self, evidence: PreflightInput) -> PreflightResult:
        reasons: list[str] = []
        if not evidence.source_refs.get("bl"):
            reasons.append("missing authoritative source refs: bl")
        if evidence.bl_status.lower() not in self.ACTIONABLE:
            reasons.append(f"BL status is not actionable: {evidence.bl_status}")
        status = PreflightStatus.PASS if not reasons else PreflightStatus.BLOCK
        return PreflightResult(status, tuple(reasons), evidence)


class DesignGate:
    """Step 7 gate: CAD and ADR, checked where design actually happens.

    Split out of :class:`PreflightGate` by BL-4029 L4.  Step 7 is
    ``sol_design_review_pass`` -- the phase in which a CAD or ADR would be
    authored.  Checking for them at step 4 demanded the design before the
    design step.

    Deliberately NOT relocated here: Brain/Obsidian freshness.  CLAUDE.md puts
    the Brain node under ETTER, so it belongs to step 13
    (``postcommit_readback``) as a closeout assertion -- never an entry
    condition.  See :class:`DefinitionOfDone`.
    """

    CAD_OK: frozenset[str] = frozenset({"verified", "fresh", "accepted"})
    ADR_OK: frozenset[str] = frozenset({"accepted", "verified", "fresh"})

    def evaluate(self, evidence: PreflightInput) -> PreflightResult:
        reasons: list[str] = []
        missing = tuple(r for r in ("cad", "adr") if not evidence.source_refs.get(r))
        if missing:
            reasons.append("missing authoritative source refs: " + ", ".join(missing))
        if evidence.cad_status.lower() not in self.CAD_OK:
            reasons.append(f"CAD status is not fresh/verified: {evidence.cad_status}")
        if evidence.adr_status.lower() not in self.ADR_OK:
            reasons.append(f"ADR status is not accepted/fresh: {evidence.adr_status}")
        status = PreflightStatus.PASS if not reasons else PreflightStatus.BLOCK
        return PreflightResult(status, tuple(reasons), evidence)


@dataclass(frozen=True)
class FaberGoal:
    goal_id: str
    title: str
    owner: str = "faber"
    projection: str = "code"
    state: GoalState = GoalState.CANDIDATE
    cad_ref: str = ""
    adr_ref: str = ""
    bl_ref: str = ""
    rollback: str = ""
    evidence: Mapping[str, str] = field(default_factory=dict)
    blocked_from: GoalState | None = None
    blocker: str = ""
    next_step: str = ""


class FaberGoalRegistry:
    """Durable registry for Faber-owned operational goals."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path).expanduser() if path else None
        self._goals: dict[str, FaberGoal] = {}
        self._disk_sig: tuple[int, int, int] | None = None
        self._last_load_ok = True
        if self.path:
            self._load()

    def _refresh_if_changed(self) -> None:
        """Re-read the registry when the file changed underneath us.

        Every agent session builds a registry at startup and holds it for the
        whole session, so without this a session that started before a goal was
        promoted would never see it — the backlog would appear empty until the
        runtime was restarted, and restarting is not a step this layer may take.

        The signature is taken BEFORE the read and stamped from that same stat:
        stamping a fresh stat afterwards would pin content read a moment earlier
        against a newer file, and the session would never refresh again.
        """
        if self.path is None:
            return
        try:
            stat = self.path.stat()
        except OSError:
            return
        signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        if signature == self._disk_sig:
            return
        previous = self._goals
        self._load(signature=signature)
        # A transient unreadable file must not silently empty a live backlog:
        # reporting zero goals is the absence this class exists to prevent.
        if not self._goals and previous and not self._last_load_ok:
            self._goals = previous
            self._disk_sig = None

    def put(self, goal: FaberGoal) -> FaberGoal:
        self.put_all([goal])
        return goal

    def put_all(
        self,
        goals: "Sequence[FaberGoal]",
        *,
        refuse_overwrite_states: "frozenset[GoalState] | set[GoalState]" = frozenset(),
        allow_overwrite_ids: "Sequence[str]" = (),
    ) -> tuple[FaberGoal, ...]:
        """Persist several goals in a single durable write.

        Either every goal lands or none does: a partial batch would leave a
        half-installed backlog that reads as complete.

        ``refuse_overwrite_states`` is checked against the state on disk, read
        inside the write lock — a caller's own snapshot cannot see a goal that
        another writer advanced in the meantime, so the guard has to live here.
        """
        accepted = tuple(goals)
        for goal in accepted:
            if goal.owner != "faber" or goal.projection != "code":
                raise ValueError("goal registry accepts only Faber Code goals")
        self._merge_and_save(
            accepted,
            refuse_overwrite_states=frozenset(refuse_overwrite_states),
            allow_overwrite_ids=frozenset(allow_overwrite_ids),
        )
        return accepted

    def get(self, goal_id: str) -> FaberGoal | None:
        self._refresh_if_changed()
        return self._goals.get(goal_id)

    def all(self) -> tuple[FaberGoal, ...]:
        self._refresh_if_changed()
        return tuple(self._goals.values())

    def next_operational_goal(self) -> FaberGoal | None:
        self._refresh_if_changed()
        candidates = [
            goal for goal in self._goals.values()
            if goal.state in {GoalState.CANDIDATE, GoalState.PROPOSED, GoalState.BLOCKED}
        ]
        return sorted(candidates, key=lambda goal: goal.goal_id)[0] if candidates else None

    def _merge_and_save(
        self,
        goals: "Sequence[FaberGoal]",
        *,
        refuse_overwrite_states: "frozenset[GoalState]" = frozenset(),
        allow_overwrite_ids: "frozenset[str]" = frozenset(),
    ) -> None:
        """Apply *goals* on top of the current on-disk state, atomically.

        Held under an exclusive lock so two writers cannot interleave, and the
        on-disk state is re-read inside the lock so a stale in-memory snapshot
        never erases goals another writer added since construction.
        """
        if self.path is None:
            self._assert_overwritable(self._goals, goals, refuse_overwrite_states, allow_overwrite_ids)
            for goal in goals:
                self._goals[goal.goal_id] = goal
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(lock_path, "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                merged = self._read_disk_goals()
                self._assert_overwritable(merged, goals, refuse_overwrite_states, allow_overwrite_ids)
                merged.update({goal.goal_id: goal for goal in goals})
                self._goals = merged
                self._save()
                self._stamp_disk_signature()
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _assert_overwritable(
        current: "Mapping[str, FaberGoal]",
        goals: "Sequence[FaberGoal]",
        refuse_overwrite_states: "frozenset[GoalState]",
        allow_overwrite_ids: "frozenset[str]",
    ) -> None:
        """Refuse the whole batch if it would reset work that already advanced."""
        if not refuse_overwrite_states:
            return
        for goal in goals:
            existing = current.get(goal.goal_id)
            if (
                existing is not None
                and existing.state in refuse_overwrite_states
                and goal.goal_id not in allow_overwrite_ids
            ):
                raise ValueError(
                    f"{goal.goal_id} already advanced to {existing.state.value}; refusing to reset it"
                )

    def _stamp_disk_signature(self) -> None:
        """Record the on-disk identity of the state we just wrote."""
        if self.path is None:
            self._disk_sig = None
            return
        try:
            stat = self.path.stat()
        except OSError:
            self._disk_sig = None
            return
        self._disk_sig = (stat.st_mtime_ns, stat.st_size, stat.st_ino)

    def _read_disk_goals(self) -> dict[str, FaberGoal]:
        """Read the persisted goals, refusing to silently drop unreadable state.

        Construction stays tolerant of a corrupt file, but a *write* must not
        quietly replace state it could not parse.
        """
        if self.path is None or not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"refusing to overwrite unreadable goal registry {self.path}: {exc}") from exc
        if not isinstance(payload, list):
            raise ValueError(f"refusing to overwrite malformed goal registry {self.path}")
        return {goal.goal_id: goal for goal in (self._goal_from_item(item) for item in payload) if goal}

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for goal in self._goals.values():
            item = asdict(goal)
            item["state"] = goal.state.value
            item["blocked_from"] = goal.blocked_from.value if goal.blocked_from else None
            payload.append(item)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _goal_from_item(item: Any) -> FaberGoal | None:
        """Decode one persisted row, or None when it is not a Faber Code goal."""
        if not isinstance(item, Mapping):
            return None
        goal = FaberGoal(
            goal_id=str(item["goal_id"]),
            title=str(item["title"]),
            owner=str(item.get("owner", "faber")),
            projection=str(item.get("projection", "code")),
            state=GoalState(str(item.get("state", GoalState.CANDIDATE.value))),
            cad_ref=str(item.get("cad_ref", "")),
            adr_ref=str(item.get("adr_ref", "")),
            bl_ref=str(item.get("bl_ref", "")),
            rollback=str(item.get("rollback", "")),
            evidence=dict(item.get("evidence") or {}),
            blocked_from=(GoalState(str(item["blocked_from"]))
                         if item.get("blocked_from") else None),
            blocker=str(item.get("blocker", "")),
            next_step=str(item.get("next_step", "")),
        )
        return goal if goal.owner == "faber" and goal.projection == "code" else None

    def _load(self, *, signature: tuple[int, int, int] | None = None) -> None:
        if self.path is None or not self.path.exists():
            return
        self._last_load_ok = False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            loaded: dict[str, FaberGoal] = {}
            for item in payload if isinstance(payload, list) else []:
                goal = self._goal_from_item(item)
                if goal is not None:
                    loaded[goal.goal_id] = goal
            self._goals = loaded
            self._last_load_ok = True
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._goals = {}
        if signature is not None:
            self._disk_sig = signature
        else:
            self._stamp_disk_signature()


@dataclass(frozen=True)
class FaberHandoff:
    """Durable continuation packet for the next Faber job/tick."""

    goal_id: str
    owner: str
    projection: str
    blocked_from: GoalState
    blocker: str
    next_step: str
    required_gate: str
    evidence: Mapping[str, str] = field(default_factory=dict)


class HandoffStore:
    """Atomic profile-local handoff store for the next Faber job."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    def save(self, handoff: FaberHandoff) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(handoff)
        payload["blocked_from"] = handoff.blocked_from.value
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self) -> FaberHandoff | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return FaberHandoff(
                goal_id=str(payload["goal_id"]),
                owner=str(payload["owner"]),
                projection=str(payload["projection"]),
                blocked_from=GoalState(str(payload["blocked_from"])),
                blocker=str(payload["blocker"]),
                next_step=str(payload["next_step"]),
                required_gate=str(payload["required_gate"]),
                evidence=dict(payload.get("evidence") or {}),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None


_ALLOWED_TRANSITIONS: dict[GoalState, frozenset[GoalState]] = {
    GoalState.CANDIDATE: frozenset({GoalState.PROPOSED}),
    GoalState.PROPOSED: frozenset({GoalState.APPROVED, GoalState.CANDIDATE}),
    GoalState.APPROVED: frozenset({GoalState.PLANNED}),
    GoalState.PLANNED: frozenset({GoalState.BUILDING}),
    GoalState.BUILDING: frozenset({GoalState.VERIFIED, GoalState.PLANNED}),
    GoalState.VERIFIED: frozenset({GoalState.LANDED, GoalState.BUILDING}),
    GoalState.LANDED: frozenset({GoalState.MEASURED}),
    GoalState.MEASURED: frozenset({GoalState.LEARNED, GoalState.PROPOSED}),
    GoalState.LEARNED: frozenset({GoalState.PROPOSED}),
    GoalState.BLOCKED: frozenset({
        GoalState.PROPOSED,
        GoalState.APPROVED,
        GoalState.PLANNED,
        GoalState.BUILDING,
        GoalState.VERIFIED,
        GoalState.LANDED,
    }),
}


class GoalLedger:
    """Fail-closed state machine for Faber-owned operational goals."""

    def __init__(self, history_path: str | os.PathLike[str] | None = None):
        self.history_path = Path(history_path).expanduser() if history_path else None

    def _record(self, before: FaberGoal, after: FaberGoal) -> None:
        if self.history_path is None:
            return
        record = {
            "goal_id": after.goal_id,
            "from": before.state.value,
            "to": after.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": dict(after.evidence),
        }
        existing: list[dict[str, Any]] = []
        if self.history_path.exists():
            try:
                existing = json.loads(self.history_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    raise ValueError("goal history must contain a list")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"goal history unreadable: {exc}") from exc
        existing.append(record)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.history_path.with_suffix(self.history_path.suffix + ".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.history_path)

    def transition(
        self,
        goal: FaberGoal,
        target: GoalState,
        *,
        preflight: PreflightResult | None = None,
        review: ReviewVerdict = ReviewVerdict.PENDING,
        review_evidence: ReviewEvidence | None = None,
        evidence: Mapping[str, str] | None = None,
        landing_evidence: "LandingEvidence | None" = None,
    ) -> FaberGoal:
        if goal.owner != "faber" or goal.projection != "code":
            raise ValueError("goal is outside Faber's Code projection")
        if target is GoalState.BLOCKED:
            updated = replace(
                goal,
                state=GoalState.BLOCKED,
                blocked_from=goal.state,
                blocker=(evidence or {}).get("blocker", "gate required"),
                next_step=(evidence or {}).get("next_step", "resume after gate"),
                evidence={**goal.evidence, **(evidence or {})},
            )
            self._record(goal, updated)
            return updated
        if goal.state is GoalState.BLOCKED:
            if goal.blocked_from is None or target is not goal.blocked_from:
                raise ValueError("blocked goal may only resume at its blocked state")
        elif target not in _ALLOWED_TRANSITIONS[goal.state]:
            raise ValueError(f"invalid goal transition: {goal.state.value} -> {target.value}")
        if target in {GoalState.APPROVED, GoalState.PLANNED, GoalState.BUILDING}:
            if preflight is None or preflight.status is not PreflightStatus.PASS:
                raise PermissionError("preflight PASS required before build planning")
            missing_refs = tuple(
                name for name, value in (("cad_ref", goal.cad_ref), ("adr_ref", goal.adr_ref), ("bl_ref", goal.bl_ref))
                if not value
            )
            if missing_refs:
                raise ValueError("goal references required before build: " + ", ".join(missing_refs))
        if target is GoalState.LANDED:
            if review_evidence is None or review_evidence.verdict is not ReviewVerdict.PASS:
                raise PermissionError("complete ReviewEvidence PASS required before landing")
            if not review_evidence.diff_id or not review_evidence.reviewer:
                raise PermissionError("review diff_id and reviewer required before landing")
        if target is GoalState.LANDED:
            if landing_evidence is None:
                raise ValueError("complete landing evidence required before landed")
            done, missing = DefinitionOfDone().evaluate(landing_evidence)
            if not done:
                raise ValueError("definition of done incomplete: " + ", ".join(missing))
        required_evidence = {
            GoalState.VERIFIED: "tests",
            GoalState.MEASURED: "runtime_smoke",
            GoalState.LEARNED: "effect_metric",
        }
        required = required_evidence.get(target)
        merged = dict(goal.evidence)
        merged.update(evidence or {})
        if required and not merged.get(required):
            raise ValueError(f"evidence required for {target.value}: {required}")
        updated = replace(goal, state=target, evidence=merged)
        self._record(goal, updated)
        return updated

    def handoff(self, goal: FaberGoal, *, required_gate: str) -> FaberHandoff:
        if goal.state is not GoalState.BLOCKED or goal.blocked_from is None:
            raise ValueError("handoff requires a blocked goal")
        return FaberHandoff(
            goal_id=goal.goal_id,
            owner=goal.owner,
            projection=goal.projection,
            blocked_from=goal.blocked_from,
            blocker=goal.blocker,
            next_step=goal.next_step,
            required_gate=required_gate,
            evidence=goal.evidence,
        )


@dataclass(frozen=True)
class LandingEvidence:
    commit: str
    reviewer: ReviewVerdict
    tests: str
    readback: str
    runtime_smoke: str
    rollback: str
    brain_change_log: str
    selfstate: str
    commit_closer: str = ""
    #: BL-4029 steg 11: filene denne landingen faktisk roerer.
    #:
    #: Feltet fantes ikke, og fravaeret var selve hullet: ADR-062 V4 sjekk 2 sier
    #: «landingssettet subset lease-settet, verifisert ved commit» -- men systemet
    #: kunne ikke UTTRYKKE hvilke filer en landing roerer, saa sjekken var ikke bare
    #: uimplementert, den var uuttrykkbar.
    #:
    #: Tomt sett er IKKE «ingen filer». Det er «ukjent», og :class:`LandingScopeGate`
    #: blokkerer paa det -- se der for hvorfor.
    landing_set: tuple[str, ...] = ()


class LandingScopeGate:
    """Steg 11: lander denne endringen NOEYAKTIG det den har lov til?

    ADR-062 V4 sjekk 2, og den eneste mekaniske sjekken som forhindrer skaden
    CLAUDE.md dokumenterer (``ae832c8a4``): at en commit sveiper med seg en parallell
    stroems arbeid.

    **Det skjedde i denne oekten, for meg.** En `git add` av EN fil ble til en commit
    med 219 -- fordi indeksen deles mellom sesjoner i arbeidstreet, og `git commit`
    uten stier tar alt som ligger der. Eksplisitt `git add` er IKKE nok; det var
    regelen jeg fulgte da det skjedde.

    Sjekken er en delmengde-test, ikke en likhets-test: en landing kan roere FAERRE
    filer enn den leaset (helt legitimt -- man tar lease foer man vet hva som trengs),
    men aldri FLERE.

    TOMT LANDINGSSETT BLOKKERER. En commit uten kjent filsett er ikke «trygg fordi den
    er tom» -- den er UKJENT, og en ukjent mengde kan ikke vaere en delmengde av noe.
    Det er dagens gjennomgaaende laerdom i én gate: fravaer av data er ikke et positivt
    funn.
    """

    def evaluate(self, landing_set: Sequence[str],
                 lease_set: Sequence[str]) -> PreflightResult:
        reasons: list[str] = []
        landing = {str(p).strip() for p in landing_set if str(p).strip()}
        leased = {str(p).strip() for p in lease_set if str(p).strip()}

        if not landing:
            reasons.append(
                "landing set is empty or unknown — a commit whose file set is not "
                "known cannot be proven to be within the lease")
        if not leased:
            reasons.append("lease set is empty — nothing was leased to land into")

        outside = sorted(landing - leased)
        if outside:
            reasons.append(
                "landing set is not a subset of the lease set; would land unleased "
                f"files: {', '.join(outside[:10])}"
                + (f" (+{len(outside) - 10} more)" if len(outside) > 10 else ""))

        status = PreflightStatus.PASS if not reasons else PreflightStatus.BLOCK
        # Evidensen her er den faktiske sammenligningen, ikke en gjenfortelling av den.
        ev = PreflightInput(
            git_clean=True, lease_clear=not reasons,
            cad_status="", adr_status="", bl_status="", obsidian_status="",
            source_refs={"lease": ",".join(sorted(leased)[:5])},
        )
        return PreflightResult(status, tuple(reasons), ev)


class DefinitionOfDone:
    """Post-work gate; all fields must be present and non-empty."""

    def evaluate(self, evidence: LandingEvidence) -> tuple[bool, tuple[str, ...]]:
        missing = tuple(
            name
            for name, value in (
                ("commit", evidence.commit),
                ("commit_closer", evidence.commit_closer),
                ("reviewer_pass", evidence.reviewer.value if evidence.reviewer is ReviewVerdict.PASS else ""),
                ("tests", evidence.tests),
                ("readback", evidence.readback),
                ("runtime_smoke", evidence.runtime_smoke),
                ("rollback", evidence.rollback),
                ("brain_change_log", evidence.brain_change_log),
                ("selfstate", evidence.selfstate),
            )
            if not value
        )
        return not missing, missing


@dataclass(frozen=True)
class PostcommitResult:
    success: bool
    evidence: LandingEvidence | None
    missing: tuple[str, ...] = ()
    error: str = ""
    #: BL-4029 A3: which steps were REPLAYED from the journal and which were
    #: actually EXECUTED this run. Without this, "success" cannot be read as a
    #: claim about work having happened.
    replayed: tuple[str, ...] = ()
    executed: tuple[str, ...] = ()


class PostcommitLoop:
    """Execute and persist the complete postcommit Definition of Done."""

    def __init__(
        self,
        *,
        readback_path: str | os.PathLike[str] | None = None,
        journal: StepJournal | None = None,
        idempotency_prefix: str = "postcommit",
    ):
        self.readback_path = Path(readback_path).expanduser() if readback_path else None
        self.journal = journal
        self.idempotency_prefix = idempotency_prefix

    def run(
        self,
        *,
        commit: str,
        reviewer: ReviewVerdict,
        tests: Callable[[], str],
        commit_closer: Callable[[str], str],
        brain_change_log: Callable[[str], str],
        selfstate: Callable[[str], str],
        readback: Callable[[str], str],
        runtime_smoke: Callable[[str], str],
        rollback: Callable[[str], str],
    ) -> PostcommitResult:
        values: dict[str, str] = {"commit": commit}
        steps: tuple[tuple[str, Callable[[str], str]], ...] = (
            ("commit_closer", lambda c: commit_closer(c)),
            ("brain_change_log", lambda c: brain_change_log(c)),
            ("selfstate", lambda c: selfstate(c)),
            ("readback", lambda c: readback(c)),
            ("runtime_smoke", lambda c: runtime_smoke(c)),
            ("rollback", lambda c: rollback(c)),
            ("tests", lambda c: tests()),
        )
        # BL-4029 A3: steps that must be RE-VERIFIED rather than replayed.
        # The inherited version replayed a recorded string for every step,
        # including tests and runtime_smoke -- so anyone able to write the
        # journal file made postcommit report DONE without a single step
        # running. That is BL-3673's "write a record to make a gate pass"
        # reappearing one layer down. Replay is legitimate for steps that only
        # RECORD something; it is never legitimate for steps that PROVE
        # something.
        never_replay = {"tests", "runtime_smoke"}
        replayed: list[str] = []
        executed: list[str] = []
        try:
            for name, callback in steps:
                journal_key = f"{self.idempotency_prefix}:{commit}:{name}"
                existing = self.journal.get(journal_key) if self.journal is not None else None
                if (existing is not None
                        and existing.get("status") in {"DONE", "ALREADY_DONE"}
                        and name not in never_replay):
                    value = str((existing.get("result") or {}).get("evidence") or "").strip()
                    replayed.append(name)
                else:
                    value = str(callback(commit) or "").strip()
                    executed.append(name)
                if not value:
                    return PostcommitResult(False, None, (name,), f"postcommit step returned empty evidence: {name}")
                values[name] = value
                if self.journal is not None and existing is None:
                    self.journal.complete(journal_key, result={"evidence": value})
            evidence = LandingEvidence(
                commit=values["commit"], reviewer=reviewer, tests=values["tests"],
                readback=values["readback"], runtime_smoke=values["runtime_smoke"],
                rollback=values["rollback"], brain_change_log=values["brain_change_log"],
                selfstate=values["selfstate"], commit_closer=values["commit_closer"],
            )
            done, missing = DefinitionOfDone().evaluate(evidence)
            if not done:
                return PostcommitResult(False, evidence, missing, "DefinitionOfDone failed")
            if self.readback_path is not None:
                self.readback_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.readback_path.with_suffix(self.readback_path.suffix + ".tmp")
                tmp.write_text(json.dumps(asdict(evidence), default=str, indent=2) + "\n", encoding="utf-8")
                tmp.replace(self.readback_path)
            # "success" must never be ambiguous about whether the work ran.
            return PostcommitResult(True, evidence, replayed=tuple(replayed),
                                    executed=tuple(executed))
        except Exception as exc:
            return PostcommitResult(False, None, (), f"postcommit exception: {exc}")


@dataclass(frozen=True)
class GovernedRunResult:
    goal: FaberGoal
    handoff: FaberHandoff | None = None
    blocker: str = ""


#: Gate values that need no separate owner decision.  "autonomt" and "reviewer"
#: come from the Flyby intake vocabulary (see tools/flyby_tools.py); the empty
#: string covers goals predating the gate field.  Anything else — including an
#: unrecognised value — is treated as an owner gate and fails closed.
_SELF_CLEARING_GATES = frozenset({"", "autonomt", "reviewer"})


def owner_gate_block(goal: FaberGoal) -> str:
    """Return the owner gate holding *goal*, or "" when none does.

    Single source for the rule so a reader (the observe tick) and the runner can
    never disagree about whether a goal is free to advance.
    """
    gate = str(goal.evidence.get("gate", "")).strip().lower()
    if gate in _SELF_CLEARING_GATES:
        return ""
    if str(goal.evidence.get("owner_approval", "")).strip():
        return ""
    return gate


class GovernedCodeRunner:
    """Single fail-closed runner for Faber's Code workflow.

    Callbacks are injected adapters for build/test/review/landing evidence.
    The runner owns ordering and state transitions; it never commits or starts
    infrastructure itself.
    """

    def __init__(self, ledger: GoalLedger | None = None):
        self.ledger = ledger or GoalLedger()

    def run(
        self,
        goal: FaberGoal,
        *,
        preflight: PreflightResult,
        build: Callable[[], Mapping[str, str]],
        review: Callable[[Mapping[str, str]], ReviewVerdict | ReviewEvidence],
        landing: Callable[[Mapping[str, str]], LandingEvidence],
        prelanding_evidence: LandingEvidence | None = None,
    ) -> GovernedRunResult:
        def blocked(current: FaberGoal, reason: str, gate: str, next_step: str) -> GovernedRunResult:
            blocked_goal = self.ledger.transition(
                current,
                GoalState.BLOCKED,
                evidence={"blocker": reason, "next_step": next_step},
            )
            return GovernedRunResult(
                blocked_goal,
                self.ledger.handoff(blocked_goal, required_gate=gate),
                reason,
            )

        if preflight.status is not PreflightStatus.PASS:
            return blocked(goal, "; ".join(preflight.reasons), "preflight", "refresh source evidence")
        # BL-4029 L4 (rettet): step 5 = bl_gate. The check used to live in
        # PreflightGate, which was circular -- step 4 cannot demand step 5's
        # output. Relocating it is only real if something CALLS it here; the
        # first attempt at L4 moved these checks into classes with zero call
        # sites, which was a net removal of four checks with a green suite
        # over it.
        bl = BlGate().evaluate(preflight.evidence)
        if bl.status is not PreflightStatus.PASS:
            return blocked(goal, "; ".join(bl.reasons), "bl_gate",
                           "land real work against the BL number, or allocate one")
        owner_gate = owner_gate_block(goal)
        if owner_gate:
            return blocked(
                goal,
                f"owner gate '{owner_gate}' requires an explicit recorded decision",
                "owner_gate",
                f"obtain the {owner_gate} decision and record it as evidence['owner_approval']",
            )
        try:
            current = self.ledger.transition(goal, GoalState.PROPOSED)
            current = self.ledger.transition(current, GoalState.APPROVED, preflight=preflight)
            current = self.ledger.transition(current, GoalState.PLANNED, preflight=preflight)
            # BL-4029 L4 (rettet): step 7 = sol_design_review_pass, the phase in
            # which a CAD or ADR is authored. Checked HERE, immediately before
            # step 8 (faber_implementation) -- not at step 4, where the design
            # does not exist yet.
            design = DesignGate().evaluate(preflight.evidence)
            if design.status is not PreflightStatus.PASS:
                return blocked(current, "; ".join(design.reasons), "design_gate",
                               "author or refresh the CAD/ADR before implementation")
            current = self.ledger.transition(current, GoalState.BUILDING, preflight=preflight)
            evidence = dict(build())
            if not evidence.get("tests"):
                return blocked(current, "build returned no test evidence", "tests", "run targeted tests")
            current = self.ledger.transition(current, GoalState.VERIFIED, preflight=preflight, evidence=evidence)
            review_result = review(evidence)
            if not isinstance(review_result, ReviewEvidence):
                return blocked(
                    current,
                    "review evidence must include matching diff_id and reviewer",
                    "reviewer",
                    "return ReviewEvidence with non-empty diff_id and reviewer",
                )
            verdict = review_result.verdict
            expected_diff = str(evidence.get("diff_id", ""))
            if not expected_diff or not review_result.diff_id or not review_result.reviewer:
                return blocked(
                    current,
                    "review evidence has missing diff_id or reviewer",
                    "reviewer",
                    "return complete ReviewEvidence",
                )
            if review_result.diff_id != expected_diff:
                return blocked(
                    current,
                    f"review diff mismatch: expected {expected_diff}, got {review_result.diff_id}",
                    "reviewer",
                    "review the current diff",
                )
            if verdict is not ReviewVerdict.PASS:
                return blocked(current, f"review verdict: {verdict.value}", "reviewer", "address review findings")
            if prelanding_evidence is None:
                return blocked(current, "prelanding DoD evidence missing", "postcommit", "prepare and verify DoD evidence before landing")
            # BL-4029 steg 11 / ADR-062 V4 sjekk 2. Plassert FOER DefinitionOfDone,
            # fordi et landingssett utenfor leasen skal stoppe kjeden uansett hvor
            # komplett resten av evidensen er. En perfekt DoD paa en commit som
            # sveiper andres filer er fortsatt et sveip.
            lease_set = tuple(str(preflight.evidence.source_refs.get("lease", "")).split(","))
            scope = LandingScopeGate().evaluate(prelanding_evidence.landing_set, lease_set)
            if scope.status is not PreflightStatus.PASS:
                return blocked(current, "; ".join(scope.reasons), "landing_scope",
                               "land only files covered by the lease, or extend the lease")
            done, missing = DefinitionOfDone().evaluate(prelanding_evidence)
            if not done:
                return blocked(current, "prelanding DoD incomplete: " + ", ".join(missing), "postcommit", "complete DoD before landing")
            landing_evidence = landing(evidence)
            current = self.ledger.transition(
                current,
                GoalState.LANDED,
                review=verdict,
                review_evidence=review_result,
                landing_evidence=landing_evidence,
                evidence={"commit": landing_evidence.commit},
            )
            return GovernedRunResult(current)
        except Exception as exc:
            return blocked(goal, f"runner exception: {type(exc).__name__}: {exc}", "runner", "inspect and retry")
