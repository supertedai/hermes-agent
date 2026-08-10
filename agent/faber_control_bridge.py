"""faber_control_bridge.py — Faber inn i loopen, ikke ved siden av den (BL-4029 L6+L7).

## Hva som manglet

To parallelle oppgave-verdener som ikke visste om hverandre:

    faber/goals.json          7 mål — det `faber_observe` og PreflightGate ser
    MWP ControlTask/kanban    det `mwp_control_plane` og de 13 stegene er bygget for

Kontrollplanet er ferdig og substansielt: `AUTOCODER_13_STEPS`, 16 `TaskState`,
fire `GateVerdict`, `dry_run_13_step()`. **Men `dry_run_13_step` ble kalt av tre
filer — seg selv, entrypointet, og testene. Null i cron, null i systemd.**

Stillaset var ikke fraværende. Det var ikke koblet. Denne modulen kobler det.

## Hva «i loopen» betyr her, presist

Etter denne modulen kjører Faber faktisk de 13 stegene mot sine egne mål, hver tick,
og **hvert steg får en status som blir registrert over tid**. Det er forskjellen på
å observere at noe er blokkert, og å vite HVILKET STEG det er blokkert på — og se om
det flytter seg.

`faber_observe` svarer «preflight BLOCK». Denne svarer «steg 4 av 13, gate BLOCK,
stegene 5-13 NOT_EXECUTED», og journalen (BL-4006) husker det, slik at
`unchanged_ticks` blir per-steg i stedet for per-mål.

## Hva den IKKE gjør, og hvorfor det er riktig

**Ingen sideeffekter.** `dry_run_13_step` heter det den heter: den planlegger alle
13 stegene uten å utføre noen av dem. Steg 6 (claim/lease), 8 (build), 11 (landing),
12 (runtime smoke) og 13 (postcommit) rapporteres som `NOT_EXECUTED` med begrunnelse.

Det er ikke skygge-modus av forsiktighet — det er ADR-062 V5. Å gi denne stien
landingsevne er en autonomi-grense-endring og hard-limit #3, altså Mortens
beslutning. Det modulen gir er at **beslutningen kan tas på et målt grunnlag**:
i dag vet ingen hvor kjeden faktisk stopper, fordi ingen har kjørt den.

Skillet er verdt å holde skarpt: *shadow* betyr at ingen ser resultatet.
Dette resultatet blir lest, journalført og dømt av `faber_fitness` — det
påvirker, det lander bare ikke.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

_MWP = os.environ.get("MWP_REPO", "/home/agent/agent-layer/mwp-uosh-automation-01")

#: Roeetter en kodelastesti har lov aa peke inn i. Se _load_control_plane.
_ALLOWED_MWP_ROOTS = (
    Path("/home/agent/agent-layer"),
    Path("/home/agent/mwp-uosh-agi-export-staging"),
)


def _load_control_plane():
    """Last MWPs kontrollplan PAA FILSTI, ikke som pakke.

    BEGGE traerne har en toppnivaa-pakke som heter `agent`: hermes-agent og
    mwp-uosh-automation-01. Et `sys.path.insert` hjelper ikke — `agent` er
    allerede bundet til hermes-agent naar denne modulen kjoerer, saa
    `from agent.mwp_control_plane import ...` gir ModuleNotFoundError.

    Det er to-verdener-problemet (L6) gjort konkret i importsystemet, og det er
    verdt aa merke seg: navnekollisjonen mellom de to trearene er ikke bare
    organisatorisk, den er mekanisk.
    """
    import importlib.util

    # SIKKERHET: `MWP_REPO` velger HVILKEN PYTHON-FIL SOM KJOERES. Den som kan sette
    # miljoeet til denne prosessen faar dermed vilkaarlig kodeutfoerelse som `agent`
    # -- en lavere terskel enn den ser ut paa en boks der cron, systemd user units og
    # denne broen arver miljoe fra hver sine steder. Defaulten er riktig og variabelen
    # er usatt i drift, men en kodelastesti maa vaere allow-listet, ikke fri.
    resolved = Path(_MWP).expanduser().resolve()
    if not any(resolved == root or root in resolved.parents for root in _ALLOWED_MWP_ROOTS):
        raise PermissionError(
            f"MWP_REPO peker utenfor tillatt rot: {resolved}. "
            f"Tillatt: {[str(r) for r in _ALLOWED_MWP_ROOTS]}")

    path = resolved / "agent" / "mwp_control_plane.py"
    if not path.exists():
        raise ModuleNotFoundError(f"MWPs kontrollplan finnes ikke: {path}")
    spec = importlib.util.spec_from_file_location("_mwp_control_plane", path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"kunne ikke laste {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mwp_control_plane"] = mod
    spec.loader.exec_module(mod)
    return mod


_cp = _load_control_plane()
Axis = _cp.Axis
ControlTask = _cp.ControlTask
DryRunStatus = _cp.DryRunStatus
GateVerdict = _cp.GateVerdict
IdentitySnapshot = _cp.IdentitySnapshot
TaskState = _cp.TaskState
dry_run_13_step = _cp.dry_run_13_step


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


#: Kartlegging fra Faber-målets tilstand til kontrollplanets. Bevisst konservativ:
#: et mål vi ikke kjenner tilstanden til blir DISCOVERY, aldri noe lenger framme.
#: Å gjette et mål lenger fram enn det er ville flyttet det forbi gater det ikke
#: har passert — samme klasse som å skrive en status for å åpne en port.
_STATE_MAP = {
    "candidate": TaskState.DISCOVERY,
    "proposed": TaskState.CLASSIFIED,
    "approved": TaskState.PLANNED,
    "planned": TaskState.PLANNED,
    "building": TaskState.RUNNING,
    "verified": TaskState.VERIFYING,
    "reviewed": TaskState.REVIEW,
    "landed": TaskState.CLOSED,
    "blocked": TaskState.BLOCKED,
}


#: Gater som IKKE krever en eier-beslutning foer planlegging. `reviewer` staar her
#: fordi steg 10 ER den kanoniske reviewer-gaten: aa blokkere paa steg 1 for at et
#: maal trenger review, hindrer kjeden i aa produsere artefaktet reviewer skal se.
#: Det er samme sirkularitet som BL-4003, ett lag opp. Samme vokabular som
#: `code_workflow.owner_gate_block` allerede bruker paa hermes-agent-siden.
_PLANNING_AUTONOMOUS_GATES = frozenset({"", "autonomt", "reviewer"})


def _required_gate(goal: dict[str, Any], ev: dict[str, Any]) -> str:
    """Hvilken gate maa avgjoeres av en EIER foer planlegging kan starte?

    FELLE JEG GIKK I FOERST: feltet heter `gate`, men naboen `gate_class` sier hva
    det er — for det foerste maalet: `"reviewer/LANDING gate"`. Jeg mappet `gate`
    rett inn i `required_gate`, som kontrollplanet leser som «krever eier-beslutning
    foer noe som helst», og alle sju maalene ble avvist paa STEG 1 av 13.

    Maalt: 4 av 7 har `reviewer`, 3 har `morten`. Kun `morten` er en ekte eier-gate.
    `reviewer` er steg 10, altsaa inne i kjeden — den skal stoppe LANDING, ikke
    PLANLEGGING.

    Et ukjent gate-navn behandles som eier-gate. Fail-closed: en gate vi ikke
    kjenner skal ikke slippe forbi fordi tabellen er ufullstendig.
    """
    raw = str(goal.get("gate", "") or ev.get("gate", "")).strip().lower()
    return "" if raw in _PLANNING_AUTONOMOUS_GATES else raw


def control_task_from_goal(goal: dict[str, Any], principal: str) -> ControlTask:
    """Projiser ett Faber-mål inn i kontrollplanets vokabular.

    Feltene som ikke finnes settes TOMME, ikke gjettet. Kontrollplanet har egne
    gater som leser dem, og en oppdiktet verdi ville åpnet en gate på et grunnlag
    som ikke finnes — nøyaktig BL-3673-defekten.
    """
    ev = goal.get("evidence") or {}
    state_raw = str(goal.get("state", "")).strip().lower()
    return ControlTask(
        mwp_id=str(goal.get("goal_id", "")),
        case_id=str(ev.get("candidate_key", "") or goal.get("goal_id", "")),
        task_id=str(goal.get("goal_id", "")),
        principal_id=principal,
        axis=Axis.AGENT,
        state=_STATE_MAP.get(state_raw, TaskState.DISCOVERY),
        owner=str(goal.get("owner", "")),
        scope=str(ev.get("repo_scope", "")),
        required_gate=_required_gate(goal, ev),
        evidence_refs=tuple(x for x in (goal.get("bl_ref"), goal.get("adr_ref"),
                                        goal.get("cad_ref")) if x),
        rollback_ref=str(goal.get("rollback", "")),
        model_role="faber",
    )


def identity_for(principal: str) -> IdentitySnapshot:
    """Identiteten Faber kjører under.

    `.15` har ingen graf-kreditiv (ADR-061), så denne er lokal og bevisst mager.
    Den er ærlig om det: en identitet uten ekstern bekreftelse skal ikke se ut som
    en bekreftet identitet.
    """
    return IdentitySnapshot(
        mode="local",
        verdict="UNVERIFIED",
        principal_id=principal,
        role="faber",
        client_session_id="",
        durable_session_id="",
    )


def run_goal(goal: dict[str, Any], all_tasks: dict[str, ControlTask],
             principal: str) -> dict[str, Any]:
    """Kjør de 13 stegene for ett mål. Ingen sideeffekter."""
    task = control_task_from_goal(goal, principal)
    result = dry_run_13_step(task, all_tasks, identity_for(principal))

    steps = []
    stopped_at = None
    for s in result.steps:
        entry = {
            "number": getattr(s, "number", None),
            "name": getattr(s, "name", ""),
            "status": getattr(getattr(s, "status", None), "value", str(getattr(s, "status", ""))),
            "gate": getattr(getattr(s, "gate", None), "value", str(getattr(s, "gate", ""))),
            "note": getattr(s, "note", ""),
        }
        steps.append(entry)
        if stopped_at is None and entry["status"] in {DryRunStatus.BLOCKED.value}:
            stopped_at = entry

    return {
        "goal_id": task.mwp_id,
        "task_state": task.state.value,
        "scope": task.scope[:80],
        # DETTE er det nye: ikke «blokkert», men blokkert PAA HVILKET STEG av 13.
        "stopped_at_step": stopped_at["number"] if stopped_at else None,
        "stopped_at_name": stopped_at["name"] if stopped_at else None,
        "stopped_reason": stopped_at["note"] if stopped_at else "",
        "steps_planned": sum(1 for s in steps if s["status"] == DryRunStatus.PLANNED.value),
        "steps_not_executed": sum(1 for s in steps if s["status"] == DryRunStatus.NOT_EXECUTED.value),
        "steps": steps,
    }


def run_all(goals: Sequence[dict[str, Any]], principal: str) -> dict[str, Any]:
    tasks = {g.get("goal_id", ""): control_task_from_goal(g, principal) for g in goals}
    per_goal = [run_goal(g, tasks, principal) for g in goals]

    # Hvor langt kommer kjeden faktisk? Aggregatet er det Morten spurte om:
    # «har Hermes en fungerende 13-stegs flyt» — dette er tallet som svarer.
    reached = [g["stopped_at_step"] for g in per_goal if g["stopped_at_step"]]
    return {
        "artifact": "faber-control-bridge-v1",
        "at": _now(),
        "principal": principal,
        "goals": len(per_goal),
        "deepest_step_reached": max(reached) if reached else None,
        "shallowest_stop": min(reached) if reached else None,
        "results": per_goal,
        "not_executed_note": (
            "dry_run_13_step planlegger alle 13 stegene uten sideeffekter. Steg 6/8/11/12/13 "
            "rapporteres NOT_EXECUTED med begrunnelse. Aa gi denne stien landingsevne er en "
            "autonomi-grense-endring (ADR-062 V5) og hard-limit #3 — Mortens beslutning."
        ),
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Kjør de 13 Autocoder-stegene mot Fabers egne mål. Ingen sideeffekter.")
    ap.add_argument("--goals", default=None,
                    help="sti til faber/goals.json (default: $HERMES_HOME/faber/goals.json)")
    ap.add_argument("--principal", default="faber")
    ap.add_argument("--record", default=None)
    ap.add_argument("--journal", action="store_true",
                    help="skriv per-steg-posisjon til BL-4006-journalen (læringen)")
    args = ap.parse_args(argv)

    path = Path(args.goals or (Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes-gui")))
                               / "faber" / "goals.json"))
    if not path.exists():
        print(json.dumps({"status": "BLOCK", "reason": f"finner ikke {path}"}), file=sys.stderr)
        return 2
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "BLOCK", "reason": f"uleselig {path}: {exc}"}), file=sys.stderr)
        return 2

    goals = raw if isinstance(raw, list) else raw.get("goals", [])
    out = run_all(goals, args.principal)

    if args.journal:
        # LÆRINGEN: per-STEG-posisjon inn i BL-4006-journalen, saa unchanged_ticks
        # blir «staar paa steg 4 uendret i N tick» i stedet for «blokkert».
        try:
            sys.path.insert(0, "/home/agent/agent-layer/hermes-agent")
            from agent import faber_goal_state as gs
            obs = [{
                "goal_id": r["goal_id"],
                # Fasenavnet ER laeringssignalet: journalens unchanged_ticks maaler
                # hvor lenge et maal har staatt paa SAMME STEG. "step_None_None"
                # ville vaert stoey; et maal uten stopp har naadd planleggingens
                # ende og skal si det.
                "phase": (f"step_{r['stopped_at_step']}_{r['stopped_at_name']}"
                          if r["stopped_at_step"] else
                          f"planned_through_13_awaiting_execution"),
                "outcome": "BLOCKED" if r["stopped_at_step"] else "PLANNED",
                "reasons": [r["stopped_reason"]] if r["stopped_reason"] else [],
                "gate": r["steps"][0]["gate"] if r["steps"] else "",
            } for r in out["results"]]
            # EGEN JOURNAL. MAALT 2026-08-10: da denne skrev til den samme
            # journalen som `faber_observe`, vekslet de to vokabularene
            # ("preflight" mot "step_1_directive") og nullstilte hverandres
            # unchanged_ticks hver tick -- max_unchanged_ticks laa fast paa 1 og
            # history vokste med 2 per runde. Journalen finnes for aa telle
            # «uendret i N tick»; to skrivere med ulikt fasevokabular gjoer den
            # ute av stand til aa telle forbi 1. De maaler ULIKE ting (preflight-
            # tilstand mot 13-stegs-posisjon) og skal derfor ikke dele noekkelrom.
            journal_path = (Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes-gui")))
                            / "faber" / "goal-state-13step.json")
            # INGEN `observed_at`. BL-4006s fantom-tick-vakt hopper over en tick
            # naar kilde-snapshotet er uendret -- riktig for `faber_observe`, hvor
            # observed_at identifiserer et SNAPSHOT. Her er hver kjoering en ny
            # observasjon av LEVENDE tilstand, og det finnes ikke noe snapshot aa
            # vaere foreldet mot. Maalt da jeg likevel sendte den: `_now()` har
            # sekund-opploesning, fire kjoeringer traff samme sekund, tre ble
            # SKIPPED -- seq sto paa 1 og journalen laerte ingenting.
            out["journal"] = gs.record_all(obs, path=journal_path)
            out["journal_path"] = str(journal_path)
        except Exception as exc:  # noqa: BLE001
            out["journal"] = {"status": "BLOCK", "reason": f"journalskriving feilet: {exc}"}

    blob = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    print(blob)
    if args.record:
        p = Path(args.record)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(blob + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
