"""Observe-only tick over the governed Faber backlog.

The goal registry had no caller: goals could be promoted into it and nothing
would ever look at them, so the queue's state was only knowable by hand.  This
module closes that without granting any new authority — it reads the backlog,
measures the evidence that is actually available, runs the same
:class:`PreflightGate` and owner-gate rules the runner uses, and records the
verdict.

It deliberately cannot build, review, commit, land, or start anything.  There is
no build callback to invoke and :class:`GovernedCodeRunner` is never constructed
here.  Wiring an *executing* tick is BL-3633's own scope and needs its own gate;
this one only makes the queue observable, so a goal that is stuck is visible as
stuck instead of silently absent.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.code_workflow import (
    FaberGoal,
    FaberGoalRegistry,
    PreflightGate,
    PreflightInput,
    PreflightStatus,
    owner_gate_block,
)

#: Statuses PreflightGate treats as actionable.  Mirrored here only to explain a
#: BLOCK in the readback; the gate itself remains the single decision point.
_UNKNOWN = "unknown"


@dataclass(frozen=True)
class GoalObservation:
    """What one goal's evidence actually says right now."""

    goal_id: str
    bl_ref: str
    gate: str
    state: str
    preflight: str
    stopped_by: str
    reasons: tuple[str, ...] = ()
    next_step: str = ""


@dataclass(frozen=True)
class ObserveResult:
    observed_at: str
    registry: str
    goals: int
    preflight_clear: int
    observations: tuple[GoalObservation, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "registry": self.registry,
            "goals": self.goals,
            # NOT "runnable": clearing preflight and the owner gate is necessary,
            # not sufficient. GovernedCodeRunner additionally requires test
            # evidence, a matching reviewer diff_id, a reviewer PASS and complete
            # prelanding DoD evidence, none of which this tick can know.
            "preflight_clear": self.preflight_clear,
            "action_taken": (
                "Read the governed backlog and evaluated preflight and the owner gate. "
                "No build, review, commit, landing, ACT, or service start was attempted — "
                "this tick has no capability to perform any of them. A goal counted in "
                "preflight_clear still has the runner's build/review/landing gates ahead of it."
            ),
            "observations": [
                {
                    "goal_id": o.goal_id,
                    "bl_ref": o.bl_ref,
                    "gate": o.gate,
                    "state": o.state,
                    "preflight": o.preflight,
                    "stopped_by": o.stopped_by,
                    "reasons": list(o.reasons),
                    "next_step": o.next_step,
                }
                for o in self.observations
            ],
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_is_clean(repo: str | os.PathLike[str] | None) -> bool:
    """Measure the target tree rather than assuming it.

    An unreachable or non-git path is reported dirty: unknown is not clean.
    """
    if not repo:
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and not proc.stdout.strip()


#: BL-4029 L3 -- scope tokens mapped to a CONTENT marker, never a directory or
#: remote name.  Measured 2026-08-10: four trees on .15 carry the remote
#: ``supertedai/AGI.git`` -- including ``hermes-agent`` itself -- because that
#: remote hosts disjoint lineages.  A check on name or remote answers the wrong
#: question; only content says whether the codebase is here.
SCOPE_MARKERS: dict[str, tuple[str, ...]] = {
    "agi": ("tools/self_state_aggregator.py", "apis"),
    "hermes-agent": ("agent/code_workflow.py",),
}

#: Where each scope would live on this host, if it lives here at all.
SCOPE_ROOTS: dict[str, str] = {
    "hermes-agent": "/home/agent/agent-layer/hermes-agent",
    "agi": "/home/agent/AGI",
}


def scope_is_executable_here(repo_scope: str) -> tuple[bool, str]:
    """Is the goal's target codebase present on THIS host?

    Returns ``(executable, note)``.  A scope this resolver does not recognise
    returns ``True`` with a note: an unknown scope must not be silently
    rejected -- that would turn a gap in this table into a verdict about the
    world, which is the failure class BL-4003 spent eight instances on.
    """
    text = (repo_scope or "").lower()
    named = [tok for tok in SCOPE_MARKERS if tok in text]
    if not named:
        return True, "scope not recognised by this resolver — not judged"

    missing = []
    for tok in named:
        root = Path(SCOPE_ROOTS.get(tok, ""))
        markers = SCOPE_MARKERS[tok]
        if not root or not all((root / m).exists() for m in markers):
            missing.append(tok)
    if not missing:
        return True, ""
    # A goal whose scope spans several codebases is executable here only if the
    # part that lives here is the whole of it.
    return False, (
        f"codebase absent on this host: {', '.join(missing)} "
        f"(content markers not found)"
    )


#: BL-4029 / ADR-062 krav (b) — UAVHENGIG OPPSLAG.
#:
#: `evidence["lease"]` er noe PRODUSENTEN skrev. Gaten som leser den, leser en
#: paastand — og en paastand er noeyaktig det reviewer BLOKKERTE i BL-3673
#: (`cab10c5f9`: "jeg skrev en post for aa faa en gate til aa slippe meg gjennom").
#:
#: Autoritetsruten `/surface/lease/check` paa `.12` svarer paa noe ANNET: om det
#: FINNES en lease, og hvem som eier den. Produsenten kan ikke endre det svaret uten
#: aa faktisk ta en lease -- altsaa uten at noe i verden endrer seg.
SURFACE_API = os.environ.get("SURFACE_API_URL", "http://192.168.40.12:8010")

#: Klientens hemmelighet leses fra FIL, ikke bare env. Cron-linja her setter kun
#: HERMES_HOME og leser ingen .env, saa en env-basert hemmelighet ville krevd at
#: noen redigerte crontab. En fil leses ved hver kjoering: sett den én gang, roter
#: den naar du vil, uten aa roere schedulering.
_TOKEN_FILE = os.environ.get(
    "SURFACE_RECEIPT_TOKEN_FILE",
    str(Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes-gui")))
        / ".surface_receipt_token"))


def _surface_token() -> str:
    """Env foerst (test), saa fil. Fila MAA vaere 0600.

    Feil modus gir TOM token -- altsaa "UVERIFISERT" -- framfor aa bruke en
    hemmelighet andre kan lese. En feilkonfigurasjon skal vaere synlig, ikke
    stilltiende akseptert.
    """
    env = os.environ.get("SURFACE_RECEIPT_TOKEN", "").strip()
    if env:
        return env
    try:
        f = Path(_TOKEN_FILE)
        if not f.exists():
            return ""
        if f.is_symlink():
            return ""
        st = f.stat()
        if st.st_mode & 0o077:
            return ""
        if st.st_uid != os.getuid():
            # En fil eid av en ANNEN bruker med 0600 er fortsatt lesbar for oss
            # hvis rettighetene tillater det -- men da er det ikke VAAR hemmelighet.
            return ""
        return f.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


def lease_clear_via_authority(paths: Sequence[str]) -> tuple[bool | None, str]:
    """Spoer autoriteten om leasen. Returnerer (clear, note).

    `None` betyr IKKE VERIFISERT -- og det er en tredje verdi med vilje. `False`
    ville sagt "ingen lease finnes", som er en paastand vi ikke har grunnlag for
    naar vi ikke fikk spurt. Fravaer av svar er ikke et svar; det er dagens
    gjennomgaaende laerdom, og her staar den i typen.

    Uten token returnerer vi `None` og lar kalleren falle tilbake paa evidensen --
    med noten om at den da er UVERIFISERT. Det er aerligere enn aa la et manglende
    token se ut som en manglende lease.
    """
    if not paths:
        return None, "ingen stier aa sjekke"
    token = _surface_token()
    if not token:
        return None, (f"ingen token ({_TOKEN_FILE} mangler eller har feil modus) — "
                      f"lease er UVERIFISERT, ikke fravaerende")

    import urllib.error
    import urllib.parse
    import urllib.request

    q = urllib.parse.urlencode({"paths": ",".join(paths)})
    req = urllib.request.Request(f"{SURFACE_API}/surface/lease/check?{q}",
                                 headers={"X-Surface-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return bool(data.get("lease_clear")), (
            f"autoritet: {len(data.get('held_by_me') or [])} av {len(paths)} eid, "
            f"{len(data.get('held_by_others') or [])} hos andre")
    except urllib.error.HTTPError as exc:
        return None, f"autoriteten svarte {exc.code} — UVERIFISERT"
    except Exception as exc:  # noqa: BLE001
        return None, f"autoriteten unaabar ({type(exc).__name__}) — UVERIFISERT"


def _scope_paths(repo_scope: str) -> list[str]:
    """Trekk ut filstier fra et `repo_scope` som `"hermes-agent: a.py, b.py"`."""
    tail = repo_scope.split(":", 1)[1] if ":" in repo_scope else repo_scope
    return [x.strip() for x in tail.split(",") if x.strip().endswith(".py")]


def _resolve_lease_clear(ev: Mapping[str, Any]) -> tuple[bool, str]:
    """Autoriteten avgjoer. UVERIFISERT er IKKE "clear".

    FOERSTE VERSJON FALT TILBAKE PAA `evidence["lease"]` NAAR AUTORITETEN IKKE
    SVARTE, og det var et hull produsenten selv kunne aapne:

        `_surface_token()` leser SURFACE_RECEIPT_TOKEN eller token-fila -- BEGGE
        paa `.15`, BEGGE eid av `agent`, som ER produsentens identitet. Produsenten
        kunne `rm` fila, eller `chmod 0644` den, og faa tom token -> `None` ->
        fallback -> sin egen paastand aeret.

    Ironien er skarp: modus-sjekken er en HERDINGSKONTROLL, og den var den billigste
    bryteren for aa skru verifiseringen AV. **En kontroll som feiler inn i aa stole
    paa den begrensede parten, er en kontroll den parten kan slaa av.**

    Det er ADR-062s terminus omskrevet: en tillitsgrense kan ikke uttrykkes i en fil
    den utrygge parten kan skrive -- og her: **en verifisering kan ikke avhenge av et
    kreditiv den verifiserte parten kontrollerer, og maa aldri feile aapent til dens
    paastand.**

    Naa: kan vi ikke verifisere, er svaret FALSE med en egen begrunnelse. Aa blokkere
    naar autoriteten er nede er riktig for en gate som skal hindre uautorisert
    landing -- og det gjoer et autoritets-utfall SYNLIG i stedet for at systemet
    stille faller tilbake til posturen fra foer ruten fantes.
    """
    paths = _scope_paths(str(ev.get("repo_scope", "")))
    if not paths:
        # Et maal uten filer i scope kan ikke ha en verifiserbar lease. Foer var
        # dette samme hull via en stillere vei: tom liste -> None -> produsentens
        # paastand.
        return False, "scope lister ingen filer — lease kan ikke verifiseres"

    verified, note = lease_clear_via_authority(paths)
    if verified is not None:
        return verified, note
    return False, (f"lease UVERIFISERT ({note}) — evidensen er produsentens egen "
                   f"paastand og aeres ikke")


def evidence_for(goal: FaberGoal, *, git_clean: bool) -> PreflightInput:
    """Build the goal's preflight input from what it actually recorded.

    Nothing is upgraded on the way in: a status the goal never established stays
    unknown, so the gate blocks for a reason that names the missing evidence.
    """
    ev = goal.evidence
    # PreflightGate requires an authoritative reference per source.  They are
    # read only from fields a governance step actually recorded -- a goal that
    # never established one is missing it, and the gate names it in the BLOCK.
    refs = {}
    for name, value in (
        ("git", ev.get("git_ref", "")),
        ("lease", ev.get("lease_ref", "")),
        ("cad", goal.cad_ref),
        ("adr", goal.adr_ref),
        ("bl", goal.bl_ref),
        ("obsidian", ev.get("obsidian_ref", "")),
    ):
        if str(value).strip():
            refs[name] = str(value)
    return PreflightInput(
        git_clean=git_clean,
        # ADR-062 (b): AUTORITETEN avgjoer. Uverifisert er ikke "clear" -- se
        # _resolve_lease_clear for hvorfor fallback til evidensen var et hull
        # produsenten selv kunne aapne.
        lease_clear=_resolve_lease_clear(ev)[0],
        cad_status=str(ev.get("cad_status", _UNKNOWN)),
        adr_status=str(ev.get("adr_status", _UNKNOWN)),
        bl_status=str(ev.get("bl_status", _UNKNOWN)),
        obsidian_status=str(ev.get("obsidian_status", _UNKNOWN)),
        source_refs=refs,
        **dict(zip(("scope_executable", "scope_note"),
                   scope_is_executable_here(str(ev.get("repo_scope", ""))))),
    )


def observe_goal(goal: FaberGoal, *, git_clean: bool, gate: PreflightGate) -> GoalObservation:
    """Evaluate one goal without touching it."""
    result = gate.evaluate(evidence_for(goal, git_clean=git_clean))
    # The runner's own predicate, imported rather than restated: a copy here
    # would silently diverge the moment the runner grows a condition.
    held_by = owner_gate_block(goal)
    if result.status is not PreflightStatus.PASS:
        stopped_by = "preflight"
    elif held_by:
        stopped_by = "owner_gate"
    else:
        stopped_by = "none"
    return GoalObservation(
        goal_id=goal.goal_id,
        bl_ref=goal.bl_ref,
        gate=str(goal.evidence.get("gate", "")).strip().lower() or "(unset)",
        state=goal.state.value,
        preflight=result.status.value,
        stopped_by=stopped_by,
        reasons=result.reasons,
        next_step=goal.next_step,
    )


def observe(
    registry: FaberGoalRegistry,
    *,
    repo_paths: Mapping[str, str] | None = None,
) -> ObserveResult:
    """Read the whole backlog and report what each goal is waiting for."""
    gate = PreflightGate()
    clean_cache: dict[str, bool] = {}
    observations = []
    for goal in sorted(registry.all(), key=lambda g: (g.bl_ref, g.goal_id)):
        repo = (repo_paths or {}).get(goal.goal_id, "")
        if repo not in clean_cache:
            clean_cache[repo] = git_is_clean(repo)
        observations.append(observe_goal(goal, git_clean=clean_cache[repo], gate=gate))
    return ObserveResult(
        observed_at=_now(),
        registry=str(registry.path) if registry.path else "(memory)",
        goals=len(observations),
        preflight_clear=sum(1 for o in observations if o.stopped_by == "none"),
        observations=tuple(observations),
    )


#: Ticks kept in the trail.  Bounded before anything schedules this, per BL-813:
#: an append-only file a timer writes to is unbounded by construction.
TRAIL_LIMIT = 500


def record(result: ObserveResult, path: str | os.PathLike[str]) -> Path:
    """Append the tick to a bounded trail and refresh the latest readback."""
    target = Path(path).expanduser()
    # A ".jsonl" target would make with_suffix() return the same path, so the
    # readback write would truncate the trail it had just appended to.
    trail = target.with_name(target.stem + ".trail.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(trail, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.to_json(), ensure_ascii=False) + "\n")
    try:
        lines = trail.read_text(encoding="utf-8").splitlines()
        if len(lines) > TRAIL_LIMIT:
            trail.write_text("\n".join(lines[-TRAIL_LIMIT:]) + "\n", encoding="utf-8")
    except OSError:
        pass
    target.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one observe-only tick over the governed Faber backlog. Never builds or lands."
    )
    parser.add_argument(
        "--registry",
        help="Faber goal registry (default: $HERMES_HOME/faber/goals.json)",
    )
    parser.add_argument("--record", help="Write the readback here (a .jsonl trail is kept alongside)")
    parser.add_argument("--repo", action="append", default=[], metavar="GOAL_ID=PATH",
                        help="Measure git cleanliness for a goal's target tree (repeatable)")
    def block(*reasons: str) -> int:
        # stderr, not stdout: a scheduled caller sends stdout to /dev/null because
        # --record already persists the readback, so a BLOCK printed to stdout is a
        # silent failure -- exactly the absence this module exists to remove.
        print(json.dumps({"status": "BLOCK", "reasons": list(reasons)}, ensure_ascii=False), file=sys.stderr)
        return 2

    args = parser.parse_args(argv)
    home = os.environ.get("HERMES_HOME", "").strip()
    registry_path = args.registry or (os.path.join(home, "faber", "goals.json") if home else "")
    if not registry_path:
        return block("no registry: pass --registry, or set HERMES_HOME (several Hermes profiles exist)")
    registry_path = os.path.expanduser(registry_path)
    # Reporting "0 goals" for a path that is not there is the silent absence this
    # module exists to remove, so a missing registry is a BLOCK, not an empty run.
    if not os.path.exists(registry_path):
        return block(f"registry does not exist: {registry_path}")
    repo_paths = {}
    for item in args.repo:
        goal_id, _, path = item.partition("=")
        if not goal_id or not path:
            return block(f"--repo expects GOAL_ID=PATH, got {item!r}")
        repo_paths[goal_id] = path
    result = observe(FaberGoalRegistry(registry_path), repo_paths=repo_paths)
    if args.record:
        record(result, args.record)
    print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
