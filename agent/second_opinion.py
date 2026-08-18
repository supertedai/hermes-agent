"""BL-4055 steg 10b — second opinion som REN POLITIKK.

Retningen er ENVEIS: denne modulen importerer INGENTING fra code_workflow og
har ingen sideeffekter (ingen nettverk, ingen fil-IO, ingen anthropic-import).
Klienten bor i agent/second_opinion_client.py og importeres SENT av runneren.

Kontrakt (arvet fra korpuset, reimplementert 2026-08-18 på Faber):
- En second opinion som bare påkalles når man allerede er i tvil, kalles aldri
  når man tar feil med selvtillit. To utløsere fyrer derfor UAVHENGIG av
  reviewerens selvrapport: blast-radius og governance-flate.
- Umålt konfidens behandles som en utløser, aldri som «sikker».
- UNAVAILABLE blokkerer. `None`-klient betyr «bruk den ekte», aldri «hopp over».
- BEGGE stemmer loggføres ALLTID — også ved enighet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class ChangeUnderReview:
    """Det andre-vurdereren får se. Metadata, aldri hemmeligheter."""
    diff_id: str
    reviewer: str
    verdict: str
    confidence: float | None
    changed_files: int
    changed_lines: int
    landing_set: tuple[str, ...]
    bl_ref: str = ""
    summary: str = ""


class SecondOpinionStatus(str, Enum):
    AGREE = "agree"
    DISSENT = "dissent"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SecondOpinionOutcome:
    status: SecondOpinionStatus
    #: API-ekkoet modell-id — identitet fra en kanal produsenten ikke setter.
    #: Tom streng = ikke verifisert (kun lovlig for UNAVAILABLE).
    reviewer_model: str = ""
    reasons: tuple[str, ...] = ()
    gate: str = "second_opinion"

    @classmethod
    def unavailable(cls, reason: str, *, gate: str = "second_opinion") -> "SecondOpinionOutcome":
        return cls(status=SecondOpinionStatus.UNAVAILABLE, reasons=(reason,), gate=gate)

    @classmethod
    def agree(cls, reviewer_model: str, *, reasons: tuple[str, ...] = ()) -> "SecondOpinionOutcome":
        if not reviewer_model:
            # En enighet uten verifisert avsender er ikke en enighet — den er
            # en påstand. Fail-closed: degrader til UNAVAILABLE.
            return cls.unavailable("agree without verified reviewer model")
        return cls(status=SecondOpinionStatus.AGREE, reviewer_model=reviewer_model, reasons=reasons)

    @classmethod
    def dissent(cls, reviewer_model: str, *, reasons: tuple[str, ...]) -> "SecondOpinionOutcome":
        if not reviewer_model:
            return cls.unavailable("dissent without verified reviewer model")
        return cls(status=SecondOpinionStatus.DISSENT, reviewer_model=reviewer_model, reasons=reasons)


@dataclass(frozen=True)
class TriggerResult:
    required: bool
    reasons: tuple[str, ...]


#: Halvparten av ScopeBudget-taket (10 filer / 500 linjer): andre-mening skal
#: fyre FØR budsjettet blokkerer, ikke samtidig med det.
_BLAST_FILES = 5
_BLAST_LINES = 250

#: Governance-flaten: filer som ER kontrollmaskineriet. En endring her får
#: aldri lande på én vurderers PASS — uansett konfidens.
_GOVERNANCE_MARKERS = (
    "code_workflow", "second_opinion", "verification_evidence",
    "guard", "gate", "policy", "authorized_keys", ".githooks",
)


class SecondOpinionTrigger:
    """Utløseren. Umålt er en utløser; selvtillit er ikke et fritak."""

    def evaluate(self, change: ChangeUnderReview) -> TriggerResult:
        reasons: list[str] = []
        if change.changed_files > _BLAST_FILES or change.changed_lines > _BLAST_LINES:
            reasons.append(
                f"blast_radius:{change.changed_files}f/{change.changed_lines}l")
        touched = [p for p in change.landing_set
                   if any(m in p for m in _GOVERNANCE_MARKERS)]
        if touched:
            reasons.append("governance_surface:" + ",".join(sorted(touched)[:3]))
        if change.confidence is None:
            reasons.append("confidence_unmeasured")
        elif change.confidence < 0.8:
            reasons.append(f"confidence_low:{change.confidence}")
        return TriggerResult(required=bool(reasons), reasons=tuple(reasons))


@dataclass(frozen=True)
class Resolution:
    allow: bool
    reason: str
    gate: str
    next_step: str
    votes: dict[str, str] = field(default_factory=dict)


def resolve_disagreement(*, change: ChangeUnderReview,
                         opinion: SecondOpinionOutcome) -> Resolution:
    """Uenighetspolitikken. Loggføring av begge stemmer er UBETINGET."""
    votes = {change.reviewer or "reviewer": change.verdict}
    if opinion.reviewer_model:
        votes[opinion.reviewer_model] = opinion.status.value
    else:
        votes["second_opinion"] = opinion.status.value

    if opinion.status is SecondOpinionStatus.UNAVAILABLE:
        return Resolution(
            allow=False,
            reason="; ".join(opinion.reasons) or "second opinion unavailable",
            gate=opinion.gate,
            next_step="restore the second opinion channel; unavailable blocks, never skips",
            votes=votes)
    if opinion.status is SecondOpinionStatus.DISSENT:
        return Resolution(
            allow=False,
            reason="second opinion dissents: " + ("; ".join(opinion.reasons) or "unspecified"),
            gate="second_opinion_dissent",
            next_step="address the dissent point-by-point or escalate to owner",
            votes=votes)
    return Resolution(allow=True, reason="both reviewers agree",
                      gate="second_opinion", next_step="", votes=votes)
