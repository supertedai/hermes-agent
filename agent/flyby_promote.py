"""Promote verified Flyby candidates into the governed Faber Code backlog.

Flyby is the candidate intake layer: it stores plans and never allocates BL,
claims a lease, commits, lands, or activates ACT.  This module is the one-way
bridge named in the governed autonomous coding workflow — a candidate becomes a
queued Faber goal only once the promotion packet carries the provenance the
later gates will be measured against.

It deliberately refuses to invent evidence.  CAD, ADR, lease and preflight stay
empty/unknown unless a governance source supplied them, so :class:`PreflightGate`
keeps blocking the goal until they exist.  Promotion means "the workflow can now
see and sequence this goal", not "this goal is approved, built, or landed".
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from agent.code_workflow import FaberGoal, FaberGoalRegistry, GoalState

#: Packet fields that must be present and non-empty.  A partial packet is a
#: promotion BLOCK, never a best-effort goal with holes in its provenance.
REQUIRED_FIELDS = (
    "candidate_key",
    "slug",
    "title",
    "bl_ref",
    "gate",
    "gate_class",
    "epistemic_status",
    "repo_scope",
    "rollback",
    "next_step",
    # BL-4063 -- the three the classifier (BL-4056, step 3) asks for. They are
    # REQUIRED at the entrance, not derived later, and the difference matters:
    #
    #   MEASURED 2026-08-11: all 7 live goals reached step 1 and no further.
    #   2 classified ADR, 5 DOUBT, 0 BL. Every reason was the same shape --
    #   "ingen erklaering om tillits-/autonomi-grense; ubesvart er ikke nei".
    #
    # The classifier was right to ask and the promoter is right to refuse to
    # invent (see the module docstring). What was missing is a PLACE for the
    # answer to enter. A question no producer can answer is not a strict gate,
    # it is an unpassable one -- and the only way through an unpassable gate is
    # to fabricate, which is exactly what reviewer BLOCKed in cab10c5f9.
    #
    # Making them REQUIRED rather than optional-with-default is the whole point.
    # A default of "no" would answer the boundary question on the proposer's
    # behalf with the cheap answer, and the bias always runs toward the cheap
    # answer. Absent stays absent, and absent BLOCKs promotion.
    "trust_boundary_change",
    "new_register",
    "contract_ref",
)

#: The two boundary questions are TRISTATE on the wire: "yes" / "no" / "unknown".
#: `unknown` is a legitimate, honest answer -- it routes the task to DOUBT and
#: escalates, which is the designed behaviour. What is NOT legitimate is the
#: field being missing, because a missing field is indistinguishable from a
#: proposer who never considered the question.
_TRISTATE = ("yes", "no", "unknown")

#: Det eksplisitte ordet for «ingen kontrakt er navngitt». Et REQUIRED felt kan
#: ikke vaere tomt, og et tomt felt ville dessuten ikke skilt «ingen kontrakt»
#: fra «noen glemte feltet». Sentinelen sier hvilken av de to det er.
_NO_CONTRACT = "none-declared"

#: States a promotion must never overwrite.  Re-running the promoter is safe by
#: design; silently resetting a goal that already advanced would not be.
#: BLOCKED and PROPOSED are deliberately absent: BLOCKED is where a governed tick
#: parks a goal awaiting evidence, and PROPOSED is the runner's own first step,
#: so re-promoting either is routine rather than a reset.
ADVANCED_STATES = frozenset(GoalState) - {
    GoalState.CANDIDATE,
    GoalState.PROPOSED,
    GoalState.BLOCKED,
}

GOAL_ID_PREFIX = "faber.code.flyby:"
TRACE_ID_PREFIX = "flyby:"


class PromotionBlocked(ValueError):
    """Raised when a packet cannot be promoted without inventing evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_packet(packet: Mapping[str, Any]) -> None:
    """Fail closed on any missing, blank, or wrong-shaped promotion field."""
    missing = [
        field
        for field in REQUIRED_FIELDS
        if not str(packet.get(field, "") or "").strip()
    ]
    if missing:
        raise PromotionBlocked(
            f"promotion packet missing required fields: {', '.join(missing)}"
        )
    acceptance = packet.get("acceptance") or []
    if not isinstance(acceptance, Sequence) or isinstance(acceptance, str) or not acceptance:
        raise PromotionBlocked(
            f"{packet['slug']}: acceptance criteria must be a non-empty list"
        )
    if str(packet["bl_ref"]).strip().upper()[:3] != "BL-":
        raise PromotionBlocked(f"{packet['slug']}: bl_ref must be a BL-xxxx reference")
    # BL-4063: the boundary answers must be one of three words, not free text.
    # A proposer who writes "probably not" has not answered; the classifier
    # would read it as an unrecognised value and fall back to doubt, which
    # LOOKS like the honest path but hides that the packet was malformed.
    # Rejecting it here keeps "unknown" meaning deliberately-unknown rather
    # than accidentally-unparseable.
    for field in ("trust_boundary_change", "new_register"):
        value = str(packet[field]).strip().lower()
        if value not in _TRISTATE:
            raise PromotionBlocked(
                f"{packet['slug']}: {field} must be one of {'/'.join(_TRISTATE)}, "
                f"got {str(packet[field])!r} -- an unparseable answer is not an answer"
            )


def build_goal(packet: Mapping[str, Any], *, promoted_by: str, promoted_at: str) -> FaberGoal:
    """Turn one validated packet into a queued, fully-traceable Faber goal.

    The goal enters at ``candidate``: :class:`GovernedCodeRunner` performs the
    ``candidate -> proposed`` transition itself, so installing it as already
    proposed would dead-end the very runner meant to pick it up.
    """
    validate_packet(packet)
    slug = str(packet["slug"]).strip()
    acceptance = [str(item) for item in packet["acceptance"]]
    evidence = {
        "candidate_key": str(packet["candidate_key"]),
        "trace_id": f"{TRACE_ID_PREFIX}{slug}",
        "source": str(packet.get("source", "flyby")),
        "gate": str(packet["gate"]),
        "gate_class": str(packet["gate_class"]),
        "epistemic_status": str(packet["epistemic_status"]),
        "repo_scope": str(packet["repo_scope"]),
        "acceptance_count": str(len(acceptance)),
        "acceptance_ref": f"graph:SelfKnowledgeFact:{packet['candidate_key']}",
        "promoted_by": promoted_by,
        "promoted_at": promoted_at,
        # Evidence the promoter is not entitled to produce.  Left explicitly
        # unknown so the preflight gate blocks rather than passing on silence.
        # "reserved" and not "open": allocate_bl hands out the number and (since
        # BL-3673) mints a pending :BL node for it, but a pending node records
        # that a number was claimed -- not that there is an actionable work item.
        # PreflightGate reads "open" as actionable, so promoting a reservation as
        # open would be writing a record to make a gate pass. It stays blocked
        # until real work lands against the number.
        "bl_status": str(packet.get("bl_status", "reserved")),
        "cad_status": str(packet.get("cad_status", "unknown")),
        "adr_status": str(packet.get("adr_status", "unknown")),
        "lease": str(packet.get("lease", "not_claimed")),
        "preflight": str(packet.get("preflight", "not_run")),
        # BL-4063: passed THROUGH from the packet, never derived here. The
        # promoter carries the proposer's declaration; it does not form one.
        "trust_boundary_change": str(packet["trust_boundary_change"]),
        "new_register": str(packet["new_register"]),
        # BL-4063 / reviewer BLOCK-2: `none-declared` er en SENTINEL, ikke en
        # kontrakt. Foer denne endringen fantes noekkelen ikke, saa broen falt
        # tilbake paa `adr_ref`/`cad_ref` (faber_control_bridge:284). Med en
        # alltid-utfylt noekkel var den fallbacken DOED for hvert promotert maal,
        # og et maal med en ekte akseptert ADR klassifiserte DOUBT paa
        # «none-declared er ikke en navngitt kontrakt».
        #
        # Et paakrevd felt som alltid har en verdi kan SKYGGE for en kilde som
        # hadde et bedre svar. Sentinelen loeses derfor her, mot pakkens egne
        # refs, foer den skrives.
        "contract_ref": (str(packet["contract_ref"]).strip()
                         if str(packet["contract_ref"]).strip() != _NO_CONTRACT
                         else (str(packet.get("adr_ref", "")).strip()
                               or str(packet.get("cad_ref", "")).strip()
                               or _NO_CONTRACT)),
    }
    return FaberGoal(
        goal_id=f"{GOAL_ID_PREFIX}{slug}",
        title=str(packet["title"]),
        owner="faber",
        projection="code",
        state=GoalState.CANDIDATE,
        cad_ref=str(packet.get("cad_ref", "")),
        adr_ref=str(packet.get("adr_ref", "")),
        bl_ref=str(packet["bl_ref"]).strip(),
        rollback=str(packet["rollback"]),
        evidence=evidence,
        next_step=str(packet["next_step"]),
    )


def promote(
    packets: Iterable[Mapping[str, Any]],
    registry: FaberGoalRegistry,
    *,
    promoted_by: str,
    force_goal_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Promote every packet, or none of them.

    Goals are built and checked against the live registry first, then written in
    a single durable batch, so a failure never leaves a half-installed backlog
    that reads as complete.
    """
    promoted_at = _now()
    goals = [build_goal(packet, promoted_by=promoted_by, promoted_at=promoted_at) for packet in packets]
    forced = set(force_goal_ids)

    seen: set[str] = set()
    plan: list[tuple[FaberGoal, str]] = []
    for goal in goals:
        if goal.goal_id in seen:
            raise PromotionBlocked(f"duplicate goal_id in batch: {goal.goal_id}")
        seen.add(goal.goal_id)
        existing = registry.get(goal.goal_id)
        if existing is not None and existing.state in ADVANCED_STATES and goal.goal_id not in forced:
            raise PromotionBlocked(
                f"{goal.goal_id} already advanced to {existing.state.value}; refusing to reset it "
                f"(pass --force-goal {goal.goal_id} only with an owner decision)"
            )
        plan.append((goal, "updated" if existing is not None else "installed"))

    unknown = forced - seen
    if unknown:
        raise PromotionBlocked(f"--force-goal names goals not in this batch: {', '.join(sorted(unknown))}")

    # The precheck above gives a clear error and powers --dry-run, but the
    # authoritative guard runs inside the registry's write lock: another writer
    # may have advanced a goal since this registry was constructed.
    registry.put_all(
        [goal for goal, _ in plan],
        refuse_overwrite_states=ADVANCED_STATES,
        allow_overwrite_ids=forced,
    )
    return [
        {
            "goal_id": goal.goal_id,
            "bl_ref": goal.bl_ref,
            "state": goal.state.value,
            "candidate_key": goal.evidence["candidate_key"],
            "gate": goal.evidence["gate"],
            "action": action,
        }
        for goal, action in plan
    ]


def load_manifest(path: str | os.PathLike[str]) -> tuple[list[dict[str, Any]], str]:
    """Read a promotion manifest and return its packets plus the promoter id."""
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    packets = payload.get("promotions")
    if not isinstance(packets, list) or not packets:
        raise PromotionBlocked("manifest has no 'promotions' list")
    promoted_by = str(payload.get("promoted_by", "")).strip()
    if not promoted_by:
        raise PromotionBlocked("manifest must name 'promoted_by'")
    return packets, promoted_by


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Promote verified Flyby candidates into the governed Faber backlog."
    )
    parser.add_argument("--manifest", required=True, help="Path to a promotion manifest JSON file")
    parser.add_argument(
        "--registry",
        help="Path to the Faber goal registry, e.g. $HERMES_HOME/faber/goals.json "
             "(required for a write: there are several Hermes profiles and the wrong one is silent)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print without writing")
    parser.add_argument(
        "--force-goal",
        action="append",
        default=[],
        metavar="GOAL_ID",
        help="Overwrite one named goal that already advanced (owner decision only; repeatable)",
    )
    args = parser.parse_args()
    try:
        packets, promoted_by = load_manifest(args.manifest)
        if args.dry_run:
            promoted_at = _now()
            goals = [
                build_goal(packet, promoted_by=promoted_by, promoted_at=promoted_at)
                for packet in packets
            ]
            print(json.dumps({"status": "DRY_RUN", "goals": [asdict(goal) for goal in goals]}, default=str, ensure_ascii=False, indent=2))
            return 0
        if not args.registry:
            raise PromotionBlocked("--registry is required for a write (use --dry-run to preview)")
        registry = FaberGoalRegistry(os.path.expanduser(args.registry))
        results = promote(packets, registry, promoted_by=promoted_by, force_goal_ids=args.force_goal)
        nxt = registry.next_operational_goal()
        print(
            json.dumps(
                {
                    "status": "PROMOTED",
                    "registry": str(registry.path),
                    "promoted": results,
                    "registry_size": len(registry.all()),
                    "next_operational_goal": nxt.goal_id if nxt else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (PromotionBlocked, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCK", "reasons": [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
