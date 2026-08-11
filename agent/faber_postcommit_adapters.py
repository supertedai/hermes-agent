"""Concrete Hermes-local adapters for the Faber postcommit Definition of Done.

``PostcommitLoop`` has always been able to run the chain
``commit_closer → brain_change_log → selfstate → readback → runtime_smoke →
rollback → tests``. What did not exist was a single real implementation of those
callbacks, so the chain had only ever run against test fixtures. That is the gap
this module closes.

Scope, stated rather than implied
---------------------------------
These adapters are **Hermes-local**. ``selfstate`` writes a Faber state record
under HERMES_HOME; it does NOT write into the Symbiose graph, because that graph
has one write gate on ``.13`` and a second, ungated writer from ``.15`` would
produce exactly the unlinked facts that gate exists to prevent. Likewise
``brain_change_log`` appends to Faber's own change log in this repo, not to
Morten's Obsidian vault on ``.13``. Naming them after the surfaces they actually
touch is the point; an adapter that claimed to have written the vault would be
worse than no adapter.

Every step fails CLOSED. ``DefinitionOfDone`` treats an empty evidence string as
a missing step, so an adapter that cannot do its job returns "" and the gate
refuses the landing — it never returns a plausible sentence about work it did
not do.
"""
from __future__ import annotations

import hashlib
import json
import keyword
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.code_workflow import (
    BindMount,
    CommitReadback,
    ContainerRuntimeTarget,
    PostcommitReadbackGate,
    PreflightStatus,
    RetiredFleetGate,
    RuntimeProbe,
    RuntimeSmokeGate,
    StepBlocked,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def faber_home() -> Path:
    override = os.environ.get("HERMES_FABER_HOME")
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "faber"
    except Exception:
        return Path(os.path.expanduser("~/.hermes-gui/faber"))


def _git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd or REPO_ROOT),
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# The seven Definition-of-Done steps
# ---------------------------------------------------------------------------

def commit_closer(sha: str, *, repo: Path | None = None) -> str:
    """Verify the commit actually landed, then record its closure.

    'Landed' means reachable from HEAD — not merely that the object exists. A
    commit that exists but sits on no branch is the case a closure record would
    otherwise quietly bless.
    """
    repo = repo or REPO_ROOT
    code, subject = _git("log", "-1", "--format=%H %s", sha, cwd=repo)
    if code != 0:
        return ""
    code, _ = _git("merge-base", "--is-ancestor", sha, "HEAD", cwd=repo)
    if code != 0:
        return ""
    code, files = _git("show", "--name-only", "--format=", sha, cwd=repo)
    touched = [f for f in files.splitlines() if f.strip()] if code == 0 else []
    record = {
        "recorded_at": _now(),
        "commit": sha,
        "subject": subject.split(" ", 1)[-1] if " " in subject else subject,
        "reachable_from_head": True,
        "files": touched,
    }
    if not _append_jsonl(faber_home() / "commit-closures.jsonl", record):
        return ""
    return f"closure recorded: {sha[:12]} reachable from HEAD, {len(touched)} file(s)"


def brain_change_log(sha: str, *, repo: Path | None = None, path: Path | None = None) -> str:
    """Append to Faber's own change log.

    Named for what it touches. Morten's Obsidian vault lives on .13 and is not
    reachable from here; writing a line that claimed otherwise would be the
    failure this whole gate is meant to catch.
    """
    repo = repo or REPO_ROOT
    target = path or (repo / "docs" / "FABER_CHANGE_LOG.md")
    code, subject = _git("log", "-1", "--format=%s", sha, cwd=repo)
    if code != 0:
        return ""
    entry = f"- {_now()} · `{sha[:12]}` — {subject}\n"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(
                "# Faber change log\n\n"
                "Hermes-lokal endringslogg for Faber-landede commits. Dette er IKKE\n"
                "Mortens Obsidian-vault på `.13` — den er en separat, kuratert flate.\n\n",
                encoding="utf-8",
            )
        with target.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except OSError:
        return ""
    return f"change log appended: {target.name} <- {sha[:12]}"


def selfstate(sha: str, *, repo: Path | None = None) -> str:
    """Record Faber's own durable state for this commit — Hermes-local only."""
    repo = repo or REPO_ROOT
    code, meta = _git("log", "-1", "--format=%H%n%an%n%cI%n%s", sha, cwd=repo)
    if code != 0:
        return ""
    parts = meta.splitlines()
    if len(parts) < 4:
        return ""
    record = {
        "recorded_at": _now(),
        "kind": "faber_landing",
        "commit": parts[0],
        "author": parts[1],
        "committed_at": parts[2],
        "subject": parts[3],
        "scope": "hermes.local",
        "note": "Hermes-local Faber state. Not written to the Symbiose graph — "
                "that graph has one write gate on .13 and a second writer here "
                "would create unlinked facts.",
    }
    if not _append_jsonl(faber_home() / "selfstate.jsonl", record):
        return ""
    return f"selfstate recorded (hermes.local): {sha[:12]}"


def readback(sha: str) -> str:
    """Re-read what the previous steps wrote. Claims nothing it cannot find."""
    found = []
    for name, filename in (("closure", "commit-closures.jsonl"), ("selfstate", "selfstate.jsonl")):
        path = faber_home() / filename
        try:
            hit = any(sha in line for line in path.read_text(encoding="utf-8").splitlines())
        except OSError:
            hit = False
        if hit:
            found.append(name)
    log = REPO_ROOT / "docs" / "FABER_CHANGE_LOG.md"
    try:
        if sha[:12] in log.read_text(encoding="utf-8"):
            found.append("change_log")
    except OSError:
        pass
    if len(found) < 3:
        return ""
    return "readback confirms: " + ", ".join(found)


def runtime_smoke(sha: str, *, modules: Sequence[str] = (), repo: Path | None = None) -> str:
    """Import the modules this commit touched, in a fresh interpreter.

    A commit whose own modules cannot be imported has not landed in any sense
    that matters, however green the diff looked.
    """
    repo = repo or REPO_ROOT
    if not modules:
        code, files = _git("show", "--name-only", "--format=", sha, cwd=repo)
        if code != 0:
            return ""
        modules = [
            f[:-3].replace("/", ".")
            for f in files.splitlines()
            if f.endswith(".py") and not f.startswith("tests/")
        ]
    if not modules:
        return f"no importable module in {sha[:12]} — smoke not applicable"
    script = "import importlib\n" + "\n".join(
        f"importlib.import_module({m!r})" for m in modules
    )
    proc = subprocess.run(
        [os.environ.get("HERMES_PYTHON", ".venv/bin/python"), "-c", script],
        cwd=str(repo), capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        return ""
    return f"runtime smoke ok: imported {len(modules)} module(s)"


def rollback(sha: str, *, repo: Path | None = None) -> str:
    """Prove the commit is reversible without touching the worktree."""
    repo = repo or REPO_ROOT
    show = subprocess.run(["git", "show", sha], cwd=str(repo),
                          capture_output=True, text=True, timeout=120)
    if show.returncode != 0:
        return ""
    check = subprocess.run(["git", "apply", "--reverse", "--check", "-"],
                           cwd=str(repo), input=show.stdout,
                           capture_output=True, text=True, timeout=120)
    if check.returncode != 0:
        return ""
    return f"rollback verified: git revert {sha[:12]} applies cleanly"


def run_tests(paths: Sequence[str], *, repo: Path | None = None) -> str:
    repo = repo or REPO_ROOT
    if not paths:
        return ""
    proc = subprocess.run(
        [os.environ.get("HERMES_PYTHON", ".venv/bin/python"), "-m", "pytest", "-q", *paths],
        cwd=str(repo), capture_output=True, text=True, timeout=900,
    )
    tail = (proc.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else ""
    if proc.returncode != 0 or "passed" not in summary:
        return ""
    return f"tests: {summary}"



# ---------------------------------------------------------------------------
# BL-4052 — steg 12 (runtime_smoke) og steg 13 (postcommit_readback)
#
# De to adapterne som fantes gjorde noe SMALERE enn stegene de var koblet til:
#
#   runtime_smoke()  importerte modulene commiten roerte, i et friskt
#                    interpret PAA BYGGEVERTEN. Det beviser at kilden parser.
#                    Det sier ingenting om noen kjoerende prosess -- og steg 12
#                    handler om nettopp det.
#   readback()       leste at Fabers tre EGNE lokale filer nevnte shaen. Den
#                    leste aldri commiten tilbake fra git, saa den kunne ikke se
#                    hverken filsettet eller fremmede filer.
#
# Begge beholdes uendret (de gjoer det de heter). Det som legges til her er
# stegene selv.
# ---------------------------------------------------------------------------


def digest_of_commit_blob(sha: str, relpath: str, *, repo: Path | None = None) -> str:
    """Digest av fila SLIK DEN BLE LANDET, lest ut av commiten.

    BL-4052 (reviewer B2) -- dette er hele grunnen til at steg 12s
    digest-sammenligning kan feile i det hele tatt.

    Den forrige versjonen brukte ``sha256_of_path(host_path)`` som fasit. Men
    ``resolve_loaded_path`` returnerer per konstruksjon en sti som naas gjennom
    en BIND-MOUNT av nettopp ``host_path`` -- samme inode. ``docker exec
    sha256sum`` paa den ga derfor alltid akkurat det samme som en ny lesing av
    vertsfila. Sammenligningen var kilden mot seg selv: den kunne ikke feile,
    heller ikke naar en parallell skriver hadde overskrevet fila etter landing
    og prosessen kjoerte noe helt annet enn det commiten inneholdt.

    Det er samme defektklasse som ``docker cp``, som gaten avviser eksplisitt --
    og den satt igjen i adapteren som forsvarte mot den. Fasit maa komme fra en
    kilde containeren ikke kan paavirke: git-objektet.
    """
    repo = repo or REPO_ROOT
    # Bare EKTE filblober. Maalt: `git cat-file --filters <sha>:<katalog>` gaar
    # igjennom og returnerer treets innhold, saa en katalogsti ga en fullt
    # plausibel digest for noe som ikke er en fil -- akkurat den klassen falskt
    # positiv resten av dette steget finnes for aa stoppe. Symlink (120000) og
    # gitlink (160000) faller ut her ogsaa; steg 12 sjekker modus selv foerst,
    # for aa kunne gi den presise grunnen framfor bare \"\".
    if commit_entry_mode(sha, relpath, repo=repo) not in {"100644", "100755"}:
        return ""
    # --filters gir bytene slik de ville sett ut ved utsjekk (autocrlf,
    # smudge-filtre), men leser fortsatt fra objektdatabasen -- saa
    # uavhengigheten fra containerens/arbeidstreets versjon bestaar. Faller
    # tilbake til raa blob paa eldre git.
    for args in (["cat-file", "--filters", f"{sha}:{relpath}"],
                 ["cat-file", "blob", f"{sha}:{relpath}"]):
        try:
            proc = subprocess.run(["git", *args], cwd=str(repo),
                                  capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return ""
        if proc.returncode == 0:
            return hashlib.sha256(proc.stdout).hexdigest()
    return ""


def commit_entry_mode(sha: str, relpath: str, *, repo: Path | None = None) -> str:
    """Git-modus for en sti i en commit: "100644", "120000" (symlink), "160000" (gitlink)."""
    repo = repo or REPO_ROOT
    wanted = str(relpath).strip()
    if not wanted:
        return ""
    # ls-tree tolker argumentet som en PATHSPEC, mens cat-file resolverer en
    # LITERAL sti. Maalt: `ls-tree <sha> -- "tools/"` lister BARNA, saa den
    # foerste moden er 100644 -- vakten leste altsaa modusen til en ANNEN
    # oppfoering enn den som ville blitt hashet. Derfor kreves noeyaktig ÉN
    # oppfoering med noeyaktig dette navnet; ellers er stien ikke en entydig
    # fil i denne commiten, og da maales ingenting.
    proc = subprocess.run(["git", "ls-tree", "--full-tree", "-z", sha, "--", wanted],
                          cwd=str(repo), capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return ""
    records = [r for r in proc.stdout.split("\0") if r.strip()]
    # `len(records) != 1` er dybdeforsvar og er BEVISST beholdt selv om den er
    # uobserverbar bak navnesjekken under: et flertreffs-resultat krever glob
    # eller pathspec-magi i `wanted`, og da kan ikke det foerste treffets navn
    # vaere lik `wanted` likevel. Mutasjonstesten rapporterer den derfor som en
    # ekvivalent mutant (N2) — den staar oppfoert som forventet overlevende i
    # /tmp/mutate_iso.py, ikke som manglende dekning.
    if len(records) != 1 or "\t" not in records[0]:
        return ""
    info, _, name = records[0].partition("\t")
    if name != wanted:
        return ""
    return info.split()[0] if info.split() else ""


def _docker(*args: str, docker_cmd: Sequence[str] | None = None,
            timeout: int = 60) -> tuple[int, str, bool]:
    """Kjoer en docker-kommando. Returnerer ``(kode, utdata, binaeret_fantes)``.

    Skillet mellom «docker finnes ikke» og «docker svarte feil» er ikke
    kosmetisk: det foerste er en gyldig maaling (ingen docker => ingen lokal
    flaate), det andre er en MISLYKKET maaling og maa blokkere.
    """
    cmd = list(docker_cmd) if docker_cmd else _default_docker_cmd()
    try:
        proc = subprocess.run([*cmd, *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "docker binary not found", False
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}", True
    # BL-4052 (reviewer B9): `stdout or stderr` lot en advarsel paa stderr bli
    # lest som resultatet naar kommandoen lyktes med tom stdout -- en
    # docker-warning kunne dermed telles som et containernavn.
    if proc.returncode != 0:
        return proc.returncode, (proc.stderr or proc.stdout).strip(), True
    return 0, (proc.stdout or "").strip(), True


def _default_docker_cmd() -> list[str]:
    """Docker-kommandoen for RUNTIME-maalinger. Kan peke paa en annen vert."""
    return shlex.split(os.environ.get("HERMES_DOCKER_CMD", "docker"))


def _local_docker_cmd() -> list[str]:
    """Docker-kommandoen for ADR-043-sjekken -- alltid DENNE verten.

    BL-4052 (reviewer B9): ADR-043-sjekken brukte ``HERMES_DOCKER_CMD``, som er
    nettopp variabelen man setter til ``ssh byopus12 docker`` for aa naa flaaten
    paa ``.12``. Da spurte «er den LOKALE flaaten tom?» en fjern vert med 283
    containere, og hver eneste landing blokkerte paa ADR-043. Sjekken om denne
    verten maa stilles til denne verten.
    """
    return shlex.split(os.environ.get("HERMES_LOCAL_DOCKER_CMD", "docker"))


def local_fleet_state(*, docker_cmd: Sequence[str] | None = None) -> tuple[bool, tuple[str, ...], str]:
    """ADR-043-maaling av den LOKALE docker-flaaten: ``(probed, navn, notat)``.

    Et manglende docker-binaerfil er et POSITIVT funn om tomhet -- det kan ikke
    kjoere containere. Alt annet som feiler er en mislykket maaling, ikke en tom
    flaate, og :class:`RetiredFleetGate` blokkerer paa den.
    """
    code, out, had_binary = _docker("ps", "--format", "{{.Names}}",
                                    docker_cmd=docker_cmd or _local_docker_cmd())
    if not had_binary:
        return True, (), "docker is not installed here, so no local container can be running"
    if code != 0:
        return False, (), f"local docker did not answer: {out[:200]}"
    return True, tuple(n.strip() for n in out.splitlines() if n.strip()), ""


def docker_runtime_probe(
    *,
    container: str,
    host_path: str,
    expected_digest: str,
    docker_cmd: Sequence[str] | None = None,
) -> RuntimeProbe:
    """Maal en KJOERENDE container fra innsiden, for én landet fil.

    Bruker ``docker exec``, aldri ``docker cp``. Maalt 2026-08-11 paa
    ``efc-unified-api``: ``/repo`` er en bind-mount av ``/home/byopus/AGI``, saa
    ``docker cp`` leverer vertsfila tilbake og en diff sammenligner kilden med
    seg selv -- den kan ikke feile, heller ikke om containeren er doed.

    Hvert felt som ikke lot seg maale forblir ``None``. Ingen av dem gjettes.
    """
    target = container.strip()
    if not target:
        return RuntimeProbe(target="<unnamed>", answered=False,
                            probe_method="docker exec", note="no container named")

    code, raw, _ = _docker("inspect", target, "--format", "{{json .}}", docker_cmd=docker_cmd)
    if code != 0 or not raw:
        return RuntimeProbe(target=target, answered=False, probe_method="docker exec",
                            note=f"docker inspect failed: {raw[:200]}")
    try:
        info = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return RuntimeProbe(target=target, answered=False, probe_method="docker exec",
                            note=f"docker inspect returned unparseable JSON: {exc}")

    state = info.get("State") or {}
    config = info.get("Config") or {}
    runtime_target = ContainerRuntimeTarget(
        name=target,
        working_dir=str(config.get("WorkingDir") or ""),
        cmd=tuple(str(c) for c in (config.get("Cmd") or ())),
        mounts=tuple(
            BindMount(source=str(m.get("Source") or ""), destination=str(m.get("Destination") or ""))
            for m in (info.get("Mounts") or ())
            if m.get("Type") == "bind"
        ),
    )
    loaded_path, why = runtime_target.resolve_loaded_path(host_path)

    started_at = str(state.get("StartedAt") or "") or None
    running = bool(state.get("Running")) if "Running" in state else None

    observed_digest: str | None = None
    source_mtime: str | None = None
    if loaded_path:
        code, out, _ = _docker("exec", target, "sha256sum", loaded_path, docker_cmd=docker_cmd)
        if code == 0 and out.split():
            observed_digest = out.split()[0]
        # Epoch: entydig, og unngaar at containerens lokale tidssone smugles inn
        # i en sammenligning mot en UTC-tidsstempel. %.9Y foerst -- hele sekunder
        # gjoer at en fil skrevet inntil ett sekund ETTER prosesstart leses som
        # eldre enn den (reviewer B9). Busybox-stat kjenner bare %Y.
        for fmt in ("%.9Y", "%Y"):
            code, out, _ = _docker("exec", target, "stat", "-c", fmt, loaded_path,
                                   docker_cmd=docker_cmd)
            if code != 0:
                continue
            try:
                source_mtime = datetime.fromtimestamp(float(out.strip()), tz=timezone.utc).isoformat()
                break
            except (TypeError, ValueError):
                continue

    return RuntimeProbe(
        target=target,
        answered=True,
        running=running,
        started_at=started_at,
        loaded_path=loaded_path,
        observed_digest=observed_digest,
        expected_digest=(expected_digest or "").strip() or None,
        source_mtime=source_mtime,
        probe_method="docker exec",
        note=why,
    )


def runtime_smoke_step(
    sha: str,
    *,
    repo: Path | None = None,
    container: str = "",
    host_path: str = "",
    repo_relpath: str = "",
    no_runtime_target: str = "",
    docker_cmd: Sequence[str] | None = None,
    check_local_fleet: bool = True,
) -> str:
    """STEG 12. Kjoerer det som ble landet, faktisk?

    Tre ledd, og hvert av dem kan alene blokkere:

    1. **ADR-043** — den lokale flaaten skal vaere tom. Et avvik her betyr at en
       roeyktest kan treffe feil vert, som er den mest overbevisende falske
       PASS-en som finnes: alt svarer, ingenting er riktig.
    2. **Import** — parser og importerer kilden i det hele tatt.
    3. **Prosess** — leser den kjoerende prosessen den fila COMMITEN inneholder,
       og startet den ETTER at fila ble skrevet? Python laster kilde ved
       prosesstart, saa en oppdatert fil er ikke en oppdatert prosess.

    **Prosess-sjekken kan ikke hoppes over ved uhell** (reviewer B1). Foerste
    versjon lot ``container`` staa tom som DEFAULT og returnerte da en
    ikke-tom streng som sa at prosessen ikke var sjekket. ``DefinitionOfDone``
    leser ikke prosa -- den leser «ikke-tom» som «oppfylt», saa standardveien
    gjennom steg 12 tilfredsstilte steg 12 uten aa maale en eneste prosess.
    Det er dagens regel brutt inne i selve vakten som skulle haandheve den.
    Naa maa kalleren oppgi ENTEN et kjoeretidsmaal ENTEN en uttrykt grunn til
    at landingen ikke har noe; ingen av dem har en default som slipper igjennom.

    Blokkerer med :class:`StepBlocked` slik at begrunnelsen overlever opp til
    :class:`PostcommitLoop`.
    """
    container = container.strip()          # D5: samme normalisering som declared
    fleet_note = ""
    if not check_local_fleet:
        # D1: en hoppet-over vakt maa SES i evidensen. Uten dette var strengen
        # byte-identisk enten ADR-043 kjoerte eller ikke -- samme defektklasse
        # som B1, i funksjonen hvis B1-fiks handlet om nettopp den.
        fleet_note = "; ADR-043 local-fleet check skipped by caller"
    if check_local_fleet:
        probed, names, note = local_fleet_state()
        verdict = RetiredFleetGate().evaluate(probed=probed, container_names=names)
        if verdict.status is not PreflightStatus.PASS:
            reasons = list(verdict.reasons)
            if note and note not in " ".join(reasons):
                reasons.append(note)          # reviewer B9: ikke kast bort aarsaken
            raise StepBlocked("runtime_smoke", "; ".join(reasons))

    declared = no_runtime_target.strip()
    if container and declared:
        raise StepBlocked("runtime_smoke",
                          "both a runtime target and a no-target declaration were given — "
                          "exactly one of them can be true")
    if not container and not declared:
        raise StepBlocked(
            "runtime_smoke",
            f"no runtime target was given for {sha[:12]} and no reason was declared for having "
            "none — an import check on the build host does not show that the landed code is "
            "RUNNING, and silence about that is read downstream as if it had been measured")

    imported = _import_smoke(sha, repo=repo)

    if declared:
        # Reviewer Q2: erklaeringen er ikke verifiserbar HERFRA -- steg 12 kjenner
        # ingen container-inventar og kan ikke vite hvilke moduler som betjenes av
        # en prosess. Aa BLOKKERE paa den ville gjenskape D2 (en uunngaaelig
        # blindvei); aa tie om den ville vaere B1. Motsigelsen skrives derfor
        # SYNLIG inn i evidensen, slik at en leser ser at en landing med
        # importerbare moduler hevdet aa ikke ha noen kjoerende prosess.
        # Aa lukke den ordentlig krever container-inventaret, som bare
        # wiring-laget har -- se modul-docstringen.
        contradiction = ""
        if landed_modules(sha, repo=repo)[0]:
            contradiction = (" — NB: this landing contains importable modules, so the "
                             "declaration is asserted, not measured")
        return (f"{imported}; process check deliberately not applicable, declared reason: "
                f"{declared}{contradiction}{fleet_note}")

    if not repo_relpath.strip():
        raise StepBlocked("runtime_smoke",
                          "a runtime target was given without the repo-relative path of the "
                          "landed file — the expected digest must come from the commit, and "
                          "without the path it cannot be read from it")
    mode = commit_entry_mode(sha, repo_relpath.strip(), repo=repo)
    if mode in {"120000", "160000"}:
        kind = "a symlink" if mode == "120000" else "a submodule reference"
        raise StepBlocked("runtime_smoke",
                          f"{repo_relpath} is {kind} in commit {sha[:12]}: the commit stores the "
                          "link target, the container reads the linked content, so the two digests "
                          "can never agree — this needs the real path, not a false mismatch")
    expected = digest_of_commit_blob(sha, repo_relpath.strip(), repo=repo)
    if not expected:
        raise StepBlocked("runtime_smoke",
                          f"could not read {repo_relpath} out of commit {sha[:12]} — without the "
                          "landed content there is nothing to compare the running process against")

    probe = docker_runtime_probe(container=container, host_path=host_path,
                                 expected_digest=expected, docker_cmd=docker_cmd)
    verdict = RuntimeSmokeGate().evaluate(probe)
    if verdict.status is not PreflightStatus.PASS:
        reasons = list(verdict.reasons)
        if probe.note and probe.note not in " ".join(reasons):
            reasons.append(probe.note)
        raise StepBlocked("runtime_smoke", "; ".join(reasons))
    # Reviewer B3: paastanden er nettopp saa bred som maalingen. Mount-analysen
    # viser at fila ligger under sys.path[0] og at prosessen leser NOEYAKTIG det
    # commiten inneholder; den beviser ikke at modulen er importert av
    # entrypointet. Evidensstrengen sier derfor det den maalte, ikke mer.
    return (f"{imported}; {container} is running, started {probe.started_at}, and reads the "
            f"landed content of {repo_relpath} at {probe.loaded_path} "
            f"(sha256 {expected[:12]}) — written before that start{fleet_note}")


def is_merge_commit(sha: str, *, repo: Path | None = None) -> bool:
    """Er dette en merge? Brukt for aa si HVILKEN grunn filsettet er ukjent av.

    KJENT BEGRENSNING (bevisst, skrevet ned framfor aa oppdages ved wiring):
    en merge blokkerer BAADE steg 12 og steg 13, og det finnes ingen
    ``-m --first-parent``-vei rundt. Den arvede ``runtime_smoke()`` lot en merge
    passere med «smoke not applicable», saa dette er strengere enn foer og i
    riktig retning -- men loekka kan ikke lukkes paa en merge slik den staar.
    """
    repo = repo or REPO_ROOT
    code, parents = _git("rev-list", "--parents", "-n", "1", sha, cwd=repo)
    return code == 0 and len(parents.split()) > 2


def _module_name(path: str) -> "str | None":
    """Modulnavnet for en .py-sti, eller None om stien ikke ER en modulsti.

    BL-4052 (reviewer D2): ``f[:-3].replace("/", ".")`` ble brukt uten aa spoerre
    om resultatet var et gyldig modulnavn. 136 sporede .py-stier i dette repoet
    oversettes ikke til gyldige navn (``optional-skills/``, ``plugins/``,
    ``website/``, ``scripts/`` -- bindestreker og segmenter som ikke er
    identifikatorer), saa enhver commit som roerte én av dem BLOKKERTE steg 12
    ubetinget, uten vei rundt.

    Den forutsigbare snarveien hadde vaert aa sende ``no_runtime_target`` for aa
    slippe unna -- altsaa aa gjoere den tomme veien til en vane. En sti som ikke
    kan vaere en modul er ikke en mislykket import; den er MAALT ikke-importerbar,
    og det er en fullstendig maaling med tomt resultat.
    """
    if not path.endswith(".py") or path.startswith("tests/"):
        return None
    parts = path[:-3].split("/")
    if any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):
        return None
    return ".".join(parts)


def landed_modules(sha: str, *, repo: Path | None = None) -> "tuple[list[str], list[str]]":
    """``(importerbare modulnavn, .py-stier som ikke ER modulnavn)`` for en commit.

    Skilt ut som DATA fordi reviewer fant at Q2-flagget utledet en konklusjon av
    en ferdig formulert setning: ``if "module(s) imported" in imported``. Det
    virket, men det leste en gjengitt setning i stedet for antallet som lå rett
    ved siden av — samme defektklasse som hele denne BL-en, inne i flagget som
    ble lagt til for å fikse den. Et tall er et tall; en setning er en
    gjengivelse av et tall, og de kan skilles lag.
    """
    repo = repo or REPO_ROOT
    present = _commit_files(sha, repo=repo, only_present=True) or ()
    modules, not_modules = [], []
    for path in present:
        name = _module_name(path)
        if name:
            modules.append(name)
        elif path.endswith(".py") and not path.startswith("tests/"):
            not_modules.append(path)
    return modules, not_modules


def _commit_files(sha: str, *, repo: Path, only_present: bool = False) -> "tuple[str, ...] | None":
    """Filsettet i en commit. ``None`` naar det ikke lot seg lese.

    ``-z`` fordi git ellers oktal-siterer stier utenfor ASCII (``core.quotepath``):
    ``haandbok.md`` kom tilbake som ``"h\\303\\245ndbok.md"`` og ble av steg 13
    anklaget for aa vaere BAADE en blindpassasjer og en manglende fil -- én fil,
    rapportert som to brudd (reviewer B5).

    En MERGE gir tomt filsett fra ``diff-tree`` uten ``-m``, og tomt er her
    kontraktsfestet til aa bety «roerer ingen filer». Derfor returneres ``None``
    med begrunnelse i stedet -- ukjent, ikke tomt (reviewer B4).
    """
    code, parents = _git("rev-list", "--parents", "-n", "1", sha, cwd=repo)
    if code != 0:
        return None
    if len(parents.split()) > 2:      # sha + >1 forelder
        return None                   # merge: se is_merge_commit() for aarsaken
    args = ["diff-tree", "-r", "--no-commit-id", "--name-only", "--root", "-z"]
    if only_present:
        args.append("--diff-filter=d")   # utelat slettede stier
    proc = subprocess.run(["git", *args, sha], cwd=str(repo),
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return None
    return tuple(f for f in proc.stdout.split("\0") if f.strip())


def _import_smoke(sha: str, *, repo: Path | None = None) -> str:
    """Importer modulene commiten roerte, i et friskt interpret.

    BL-4052 -- retter et hull i den arvede ``runtime_smoke()``: naar filsettet
    var TOMT returnerte den strengen ``"no importable module ... — smoke not
    applicable"``, som er ikke-tom og derfor teller som BESTAATT i
    ``DefinitionOfDone``. Det er dagens regel brutt i selve steg 12-adapteren:
    fravaer av data ble et positivt funn.

    Skillet som mangler er mellom to helt ulike tomheter:

      * git svarte ikke, eller commiten roerer INGEN filer  -> UKJENT -> BLOCK
      * commiten roerer filer, men ingen av dem er importerbare moduler
        (ren dokumentasjon, konfig)                          -> MAALT -> OK

    Den andre er en fullstendig maaling med tomt resultat. Den foerste er ikke
    en maaling i det hele tatt.
    """
    repo = repo or REPO_ROOT
    touched = _commit_files(sha, repo=repo)
    if touched is None:
        why = ("it is a merge commit, whose file set this method does not read"
               if is_merge_commit(sha, repo=repo) else "the commit is unreadable")
        raise StepBlocked("runtime_smoke",
                          f"git could not read the file set of {sha[:12]}: {why} — an unread "
                          "commit is not a smoke-tested commit")
    if not touched:
        raise StepBlocked("runtime_smoke",
                          f"commit {sha[:12]} touches no files — there is nothing to smoke test, "
                          "and an empty change set is not a passing one")

    # Bare stier som fortsatt FINNES i commiten: en commit som sletter en modul
    # skal ikke prøve å importere den og blokkere for alltid (reviewer B6).
    modules, not_modules = landed_modules(sha, repo=repo)
    skipped = (f"; {len(not_modules)} .py path(s) are not importable module names "
               f"({', '.join(sorted(not_modules)[:3])})" if not_modules else "")
    if not modules:
        return (f"import smoke: {len(touched)} file(s) changed, none of them importable modules "
                f"(measured, not assumed){skipped}")

    script = "import importlib\n" + "\n".join(f"importlib.import_module({m!r})" for m in modules)
    try:
        proc = subprocess.run(
            [os.environ.get("HERMES_PYTHON", ".venv/bin/python"), "-c", script],
            cwd=str(repo), capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StepBlocked("runtime_smoke", f"import smoke could not run: {exc}") from exc
    if proc.returncode != 0:
        raise StepBlocked("runtime_smoke",
                          f"import failed for {len(modules)} module(s): "
                          f"{(proc.stderr or proc.stdout).strip().splitlines()[-1:] or ['']}"[:300])
    return f"import smoke: {len(modules)} module(s) imported{skipped}"


def commit_readback(sha: str, *, repo: Path | None = None) -> CommitReadback:
    """Les commiten tilbake fra git. Hevder aldri noe den ikke fant.

    ``files=None`` naar git ikke kunne svare -- det er UKJENT, ikke tomt.
    """
    repo = repo or REPO_ROOT
    code, resolved = _git("rev-parse", "--verify", f"{sha}^{{commit}}", cwd=repo)
    if code != 0:
        return CommitReadback(commit=sha, resolved=False, read_method="git rev-parse")

    code, _ = _git("merge-base", "--is-ancestor", sha, "HEAD", cwd=repo)
    reachable = code == 0

    code, subject = _git("log", "-1", "--format=%s", sha, cwd=repo)
    subject = subject if code == 0 else ""

    # --root saa en root-commit rapporterer filene sine i stedet for ingenting;
    # -z saa ikke-ASCII-stier ikke kommer tilbake oktal-siterte; merge => None.
    files = _commit_files(sha, repo=repo)

    return CommitReadback(
        commit=resolved.strip() or sha,
        resolved=True,
        reachable_from_head=reachable,
        files=files,
        subject=subject,
        read_method="git diff-tree",
    )


def postcommit_readback(
    sha: str,
    *,
    expected_files: Sequence[str],
    require_ref: str = "",
    repo: Path | None = None,
) -> str:
    """STEG 13. Finnes commiten, inneholder den noeyaktig det den skulle, og
    fulgte det noe fremmed med?

    Bruker :class:`PostcommitReadbackGate` for git-siden og den arvede
    :func:`readback` for Fabers egne lokale artefakter. Ingen av delene er
    duplisert her; dette er sammenkoblingen.
    """
    verdict = PostcommitReadbackGate().evaluate(
        commit_readback(sha, repo=repo),
        expected_files=expected_files,
        require_ref=require_ref,
    )
    if verdict.status is not PreflightStatus.PASS:
        raise StepBlocked("readback", "; ".join(verdict.reasons))

    local = readback(sha)
    if not local:
        raise StepBlocked(
            "readback",
            f"commit {sha[:12]} reads back correctly from git, but Faber's own closure, "
            "selfstate and change-log records for it could not all be found — a landing "
            "nobody recorded is a landing nobody can trace")
    return (f"readback verified: {sha[:12]} contains exactly {len(expected_files)} expected "
            f"file(s), no foreign files; {local}")


# ---------------------------------------------------------------------------
# C2 — learning measurement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LearningEvent:
    commit: str
    goal_id: str
    metric: str
    baseline: float
    after: float
    confidence: float
    status: str
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {"recorded_at": _now(), **asdict(self), "delta": self.after - self.baseline}


def record_learning(
    *,
    commit: str,
    goal_id: str,
    metric: str,
    baseline: float,
    after: float,
    method: str,
    confidence: float,
    log: Path | None = None,
) -> LearningEvent | None:
    """Persist one before/after measurement bound to a commit and a goal.

    This module refuses to *produce* the measurement. It enforces the shape —
    a named metric, both readings, how they were taken, a confidence, and a
    verdict derived from the numbers rather than asserted alongside them. A
    learning event whose baseline and after are identical is `inconclusive`,
    never `confirmed`; that is the case where a claim of learning is easiest
    to make and hardest to justify.
    """
    if not commit.strip() or not goal_id.strip() or not metric.strip() or not method.strip():
        return None
    if not 0.0 <= confidence <= 1.0:
        return None
    if after > baseline:
        status = "confirmed"
    elif after < baseline:
        status = "refuted"
    else:
        status = "inconclusive"
    event = LearningEvent(commit.strip(), goal_id.strip(), metric.strip(),
                          float(baseline), float(after), float(confidence), status, method.strip())
    target = log or (faber_home() / "learning-events.jsonl")
    if not _append_jsonl(target, event.to_dict()):
        return None
    return event
