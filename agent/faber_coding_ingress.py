"""Governed ingress for coding-relevant Hermes TUI turns into Faber.

Faber owns code. For that ownership to be real, a coding turn must arrive at
Faber with a provenance envelope, not as an anonymous string: who sent it
(``owner``), under which trace (``trace_id``), against which goal
(``goal_id``), from which surface (``provenance``), and with an explicit
readback of the gates that were evaluated (``gates``).

Two directions of failure, deliberately asymmetric
--------------------------------------------------
- **Ingest fails CLOSED.** Missing envelope fields, an unresolved consent
  grant, or an injection finding means the turn is NOT admitted to Faber. No
  gate evidence is never treated as a pass.
- **The chat turn fails OPEN.** This module never decides whether the user's
  conversation runs. Blocking Hermes chat on Faber's ingest surface would turn
  an ingest outage into a chat outage; making Faber the only authoritative code
  runtime is a separate, enactment-gated change.

The readback log intentionally stores a digest of the turn text, never the text
itself. A record for a turn that was blocked as private or injection-bearing
must not become the place that material leaks into.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Absence of a registered identity means the legacy/admin era (Morten at the
# console) — the same owner-default the recall path already applies. Recorded
# explicitly as ``legacy_default`` so a record never implies an identity the
# gateway never asserted.
LEGACY_OWNER_DEFAULT = "morten"

_CONSENT_ENV = "HERMES_FABER_INGRESS_CONSENT"
_LOG_ENV = "HERMES_FABER_INGRESS_LOG"
_FABER_HOME = Path(os.path.expanduser("~/.hermes-gui/faber"))

# Coding signals are matched conservatively: a false negative costs Faber one
# turn of context, a false positive pushes ordinary conversation into the code
# runtime's ingest surface.
_CODING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"```"),
    re.compile(r"\b[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|sh|sql|ya?ml|json|toml|md)\b"),
    re.compile(r"\b(?:git|commit|diff|patch|merge|rebase|branch|revert|PR|pull request)\b", re.I),
    re.compile(
        r"\b(?:implement|refactor|debug|deploy|compile|lint|traceback|stacktrace|"
        r"unit test|regression|repo|repository|codebase|function|classe?s?|module)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:fiks|fikse|kode|kod|implementer|refaktorer|bygg|bygge|feilsøk|"
        r"kodebase|repoet|testene)\b",
        re.I,
    ),
    re.compile(r"^\s*(?:def |class |import |from \w+ import |async def )", re.M),
)


@dataclass(frozen=True)
class IngressGate:
    """One evaluated gate. ``status`` is pass / block / unknown — never assumed."""

    name: str
    status: str
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass(frozen=True)
class CodingTurnIngress:
    """The envelope Faber receives, plus the evidence for admitting it."""

    trace_id: str
    goal_id: str
    owner: str
    owner_source: str
    coding_relevant: bool
    admitted: bool
    provenance: Mapping[str, Any]
    gates: tuple[IngressGate, ...]
    text_sha256: str
    text_len: int
    block_reasons: tuple[str, ...] = ()
    # Carried in memory for an admitted turn only. A blocked turn's content
    # never travels past the gate that blocked it — the digest above stays, so
    # the record is still correlatable without holding the material.
    text: str = field(default="", repr=False, compare=False)

    def readback(self) -> dict[str, Any]:
        """Serializable record — carries the digest of the turn, never the turn."""
        return {
            "trace_id": self.trace_id,
            "goal_id": self.goal_id,
            "owner": self.owner,
            "owner_source": self.owner_source,
            "coding_relevant": self.coding_relevant,
            "admitted": self.admitted,
            "provenance": dict(self.provenance),
            "gates": [asdict(gate) for gate in self.gates],
            "block_reasons": list(self.block_reasons),
            "text_sha256": self.text_sha256,
            "text_len": self.text_len,
        }


def is_coding_turn(text: str) -> bool:
    """True when the turn carries a code signal Faber should own."""
    if not isinstance(text, str) or not text.strip():
        return False
    return any(pattern.search(text) for pattern in _CODING_PATTERNS)


def compute_trace_id(session_key: str, turn_index: int, text: str) -> str:
    """Deterministic id so a later turn can correlate back to this one.

    Derived, not random: the same turn re-derives the same trace_id from the
    session, its ordinal and its content, which is what makes the learning
    readback in a later turn checkable rather than merely asserted.
    """
    digest = hashlib.sha256(
        f"{session_key}|{turn_index}|{text}".encode("utf-8")
    ).hexdigest()
    return f"tui:{digest[:16]}"


def consent_path() -> Path:
    override = os.environ.get(_CONSENT_ENV)
    return Path(override) if override else _FABER_HOME / "ingress-consent.json"


def log_path() -> Path:
    override = os.environ.get(_LOG_ENV)
    return Path(override) if override else _FABER_HOME / "coding-ingress.jsonl"


def evaluate_consent(owner: str, *, path: Path | None = None) -> IngressGate:
    """Read the owner's explicit grant for coding ingress.

    A missing file, a missing entry and a malformed store are all
    ``block`` — distinguished only by ``detail``. There is no state in which
    the absence of a grant is read as a grant.
    """
    store = path or consent_path()
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return IngressGate("consent", "block", f"no consent store at {store}")
    except (OSError, ValueError) as exc:
        return IngressGate("consent", "block", f"consent store unreadable: {exc}")
    grants = raw.get("grants") if isinstance(raw, dict) else None
    entry = grants.get(owner) if isinstance(grants, dict) else None
    if not isinstance(entry, dict):
        return IngressGate("consent", "block", f"no grant for owner {owner!r}")
    if entry.get("scope") != "coding_turns":
        return IngressGate("consent", "block", f"grant for {owner!r} is not scoped to coding_turns")
    if entry.get("granted") is not True:
        return IngressGate("consent", "block", f"grant for {owner!r} is not active")
    return IngressGate("consent", "pass", f"granted_by={entry.get('granted_by', '[unrecorded]')}")


def evaluate_injection(text: str) -> IngressGate:
    """Scan the turn with the repo's shared threat-pattern library.

    An unavailable scanner is ``unknown``, not ``pass``: an ingest path that
    silently stops scanning is worse than one that stops admitting.
    """
    try:
        from tools.threat_patterns import scan_for_threats
    except Exception as exc:  # pragma: no cover - import guard
        return IngressGate("injection", "unknown", f"scanner unavailable: {exc}")
    try:
        findings = scan_for_threats(text, scope="all")
    except Exception as exc:
        return IngressGate("injection", "unknown", f"scan failed: {exc}")
    if findings:
        return IngressGate("injection", "block", "findings: " + ", ".join(sorted(set(findings))))
    return IngressGate("injection", "pass", "no findings at scope=all")


def resolve_owner(session_id: str) -> tuple[str, str, IngressGate]:
    """Resolve (owner, owner_source, identity gate) for the submitting session.

    A corrupt identity store raises inside ``get_identity``; that is infra
    failure, not a legacy session, so it blocks rather than silently
    collapsing onto the owner default.
    """
    try:
        from hermes_cli.dashboard_auth.session_identity import get_identity

        identity = get_identity(session_id)
    except Exception as exc:
        return (
            "",
            "unresolved",
            IngressGate("identity", "block", f"identity store unreadable: {exc}"),
        )
    if isinstance(identity, str) and identity.strip():
        return identity.strip().lower(), "identity", IngressGate("identity", "pass", "asserted by gateway")
    return (
        LEGACY_OWNER_DEFAULT,
        "legacy_default",
        IngressGate("identity", "pass", "no asserted identity — legacy/admin era owner default"),
    )


def evaluate_coding_turn(
    text: str,
    *,
    session_key: str,
    session_id: str,
    turn_index: int,
    surface: str = "tui.prompt.submit",
    consent_store: Path | None = None,
) -> CodingTurnIngress:
    """Build the envelope and decide admission. Never raises on gate failure."""
    safe_text = text if isinstance(text, str) else ""
    coding = is_coding_turn(safe_text)
    owner, owner_source, identity_gate = resolve_owner(session_id)
    trace_id = compute_trace_id(session_key, turn_index, safe_text)
    goal_id = f"faber.code.{trace_id}" if trace_id else ""
    provenance = {
        "surface": surface,
        "session_key": session_key,
        "session_id": session_id,
        "turn_index": turn_index,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    gates: list[IngressGate] = [identity_gate]
    reasons: list[str] = []

    # A non-coding turn is not Faber's to own. It is recorded (so "why did Faber
    # never see this?" is answerable) but never admitted.
    if not coding:
        gates.append(IngressGate("relevance", "block", "no coding signal in turn"))
        reasons.append("not_coding_relevant")
    else:
        gates.append(IngressGate("relevance", "pass", "coding signal present"))

    missing = [
        name
        for name, value in (
            ("trace_id", trace_id),
            ("goal_id", goal_id),
            ("owner", owner),
            ("session_key", session_key),
            ("session_id", session_id),
        )
        if not str(value).strip()
    ]
    if missing:
        gates.append(IngressGate("envelope", "block", "missing: " + ", ".join(missing)))
        reasons.append("envelope_incomplete")
    else:
        gates.append(IngressGate("envelope", "pass", "all required fields present"))

    injection_gate = evaluate_injection(safe_text)
    gates.append(injection_gate)
    if not injection_gate.passed:
        reasons.append(f"injection_{injection_gate.status}")

    consent_gate = evaluate_consent(owner, path=consent_store) if owner else IngressGate(
        "consent", "block", "owner unresolved"
    )
    gates.append(consent_gate)
    if not consent_gate.passed:
        reasons.append(f"consent_{consent_gate.status}")

    if not identity_gate.passed:
        reasons.append(f"identity_{identity_gate.status}")

    admitted = all(gate.passed for gate in gates)
    return CodingTurnIngress(
        trace_id=trace_id,
        goal_id=goal_id,
        owner=owner,
        owner_source=owner_source,
        coding_relevant=coding,
        admitted=admitted,
        provenance=provenance,
        gates=tuple(gates),
        text_sha256=hashlib.sha256(safe_text.encode("utf-8")).hexdigest(),
        text_len=len(safe_text),
        block_reasons=tuple(dict.fromkeys(reasons)),
        text=safe_text if admitted else "",
    )


def record_coding_turn(
    text: str,
    *,
    session_key: str,
    session_id: str,
    turn_index: int,
    surface: str = "tui.prompt.submit",
    consent_store: Path | None = None,
    log: Path | None = None,
) -> CodingTurnIngress:
    """Evaluate one turn and append its readback record.

    A failed append does not change the verdict — the caller still receives the
    envelope — but it is logged rather than swallowed, so "the record exists"
    is never inferred from the call having returned.
    """
    ingress = evaluate_coding_turn(
        text,
        session_key=session_key,
        session_id=session_id,
        turn_index=turn_index,
        surface=surface,
        consent_store=consent_store,
    )
    target = log or log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(ingress.readback(), ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("faber coding-ingress readback not written to %s: %s", target, exc)
    return ingress
