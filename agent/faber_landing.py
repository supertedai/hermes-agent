"""Steg 11-utføreren: gjør landingen vakten allerede har godkjent.

BL-4051.

``LandingScopeGate`` (BL-4029 steg 11) kan DØMME et landingssett, men ingenting
UTFØRTE et. ``agent/faber_runtime.py`` ga runneren ``landing=lambda _: landing``
— en ``LandingEvidence`` en oppringer allerede hadde skrevet ned. «Landing» var
altså en påstand om en commit noen andre hadde laget, ikke en handling. Vakten
var ekte; hånden manglet.

Dette er hånden: stage nøyaktig landingssettet, commit med melding, les tilbake
hva som faktisk landet.

Hvorfor dette fortjener en egen modul
-------------------------------------
Indeksen deles av alle sesjoner i arbeidstreet (BL-3676). 2026-08-10 sveipet én
bar ``git commit`` 218 fremmede filer inn i én commit. Regelen «bruk eksplisitt
``git add``» var ikke nok — den var regelen som ble fulgt da det skjedde, fordi
``git add`` skriver til den DELTE indeksen og ``git commit`` uten stier tar alt
som ligger der.

Det som faktisk verner er ``git commit --only -- <stier>``: git bygger en
midlertidig indeks fra HEAD og henter KUN de navngitte stiene, fra arbeidstreet.
Målt under dette arbeidet: 218 stagede fremmede filer pluss én modifisert sporet
fil, og commiten inneholdt nøyaktig én fil — og de 218 overlevde i indeksen, så
parallellstrømmens arbeid ble ikke ødelagt heller.

``--only`` virker likevel ikke på filer git ikke kjenner: en ny fil må først få
en intent-to-add-oppføring (``git add -N``). Derfor ``-N`` + ``--only``, og
aldri ``git add .`` eller ``git commit -a``.

Settet kan ikke avvike fra det vakten dømte
-------------------------------------------
:func:`landing_callable` tar IKKE imot et landingssett. Det utleder settet fra
``prelanding.landing_set`` — den samme verdien :class:`~agent.code_workflow.LandingScopeGate`
måler mot leasen inne i :class:`~agent.code_workflow.GovernedCodeRunner`.

Første utkast tok begge inn som uavhengige argumenter og lot en docstring si at
de måtte være like. En review målte utfallet: vakten dømte ``('mine.py',)``,
hånden landet ``('mine.py', 'IKKE_LEASET.py')``, målet gikk til LANDED. Det er
den samme feilklassen som modulen ellers handler om — en regel som må HUSKES
framfor å være umulig å bryte. Divergensen er nå ikke representerbar.

Før-målingen er evidens, ikke vern
-----------------------------------
:meth:`GitLandingExecutor._snapshot` leser ``git ls-files`` og
``git diff --cached --name-only`` i ÉN prosess, fordi to kommandoer har et vindu
imellom der en parallell strøm kan legge noe i indeksen. Men selv ett skall
lukker ikke vinduet fram til selve commiten. Det er verdt å si rett ut:
før-målingen beviser ingenting om utfallet. ``--only`` er vernet,
:meth:`GitLandingExecutor._verify` er beviset, og før-målingen er der for at
etterkontrollen skal ha et innhold å sammenligne mot.

Etterkontrollen måler VÅR commit, ikke HEAD
-------------------------------------------
``_commit`` committer og leser SHA-en i samme prosess, og ``_verify`` spør om
den SHA-en. Et tidligere utkast spurte om ``HEAD``, og en review målte at det ga
``ok=True`` på en parallell strøms commit — tilbakelesingen navnga da en commit
denne landingen ikke hadde laget. Emnelinjen kontrolleres i tillegg, slik at en
forvekslet commit ikke kan passere stille.

``_verify`` krever at filsettet er NØYAKTIG det deklarerte — ikke en delmengde,
ikke en overmengde — og at hver fils blob i commiten er den som lå i
arbeidstreet ved før-målingen. En fremmed fil som kom med er en feil; en
deklarert fil som IKKE kom med er også en feil, fordi deklarasjonen var det
vakten dømte på.

All git-utdata som er filnavn leses NUL-separert. Uten ``-z`` skriver git om
navn med ikke-ASCII til ``"faber_l\\303\\245nding.py"``, og etterkontrollen ville
meldt både «fremmed fil» og «deklarert fil landet ikke» om en commit som var
helt riktig — en falsk-positiv i nettopp den detektoren som skal ha siste ord.

Vi ANGRER ALDRI en commit automatisk. Feiler etterkontrollen, finnes commiten
fortsatt, og SHA-en navngis i begrunnelsen. En automatisk ``reset``/``revert``
på et delt arbeidstre ville vært en ny sveip-klasse, denne gang destruktiv.

Push er ikke denne modulens jobb
---------------------------------
Hermes-repoet har TRE remotes, og ``origin`` er ``supertedai/AGI`` — ikke
hermes. En bar push herfra ville truffet feil repo. Modulen rører derfor ingen
remote i det hele tatt; den lander lokalt og lar en navngitt remote være et
bevisst, separat valg.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

from agent.code_workflow import LandingEvidence
from agent.faber_postcommit_adapters import faber_home

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Tegn som får git til å tolke en «sti» som noe annet enn én navngitt fil.
_FORBIDDEN_CHARS = ("*", "?", "[", "]", "\n", "\r", "\t")

_SNAPSHOT_SCRIPT = r"""
d=$1; shift
git rev-parse HEAD >"$d/head" 2>/dev/null || true
git ls-files -z -- "$@" >"$d/tracked" 2>/dev/null || true
git diff --cached --name-only -z >"$d/staged" 2>/dev/null || true
: >"$d/blobs"
for p in "$@"; do
  if [ -f "$p" ]; then
    h=$(git hash-object --path "$p" -- "$p" 2>/dev/null) || h=
    [ -n "$h" ] || h=UNREADABLE
  else
    h=ABSENT
  fi
  printf '%s\0%s\0' "$p" "$h" >>"$d/blobs"
done
"""

_COMMIT_SCRIPT = r"""
d=$1; shift
msg=$1; shift
git commit -m "$msg" --only -- "$@" >"$d/out" 2>&1 || exit 1
git rev-parse HEAD >"$d/sha" 2>/dev/null
"""

_VERIFY_SCRIPT = r"""
d=$1; shift
sha=$1; shift
git rev-parse --verify -q "$sha^" >"$d/parent" 2>/dev/null || true
git log -1 --format=%s "$sha" >"$d/subject" 2>/dev/null || true
git diff-tree --no-commit-id --name-only -r --root -z "$sha" >"$d/files" 2>/dev/null || true
: >"$d/blobs"
for p in "$@"; do
  h=$(git rev-parse --verify -q "$sha:$p" 2>/dev/null) || h=
  [ -n "$h" ] || h=ABSENT
  printf '%s\0%s\0' "$p" "$h" >>"$d/blobs"
done
"""

_INDEX_STATE_SCRIPT = r"""
d=$1; shift
git diff --cached --name-only -z >"$d/staged" 2>/dev/null || true
"""


def _subject_of(message: str) -> str:
    """Emnelinja slik GIT ville skrevet den, ikke slik Python deler linjer.

    ``%s`` er ikke «første linje». Git bretter første avsnitt til én linje og
    fjerner etterfølgende blanktegn; ``splitlines()[0]`` gjør ingen av delene.
    Et første avsnitt over to linjer, eller et mellomrom på slutten av tittelen,
    ga dermed «this is not the commit this landing wrote» om en commit som
    utvilsomt var vår — samme falsk-positiv-klasse som siterte filnavn og
    unormaliserte stavemåter, og like ubotelig, siden commiten allerede er gjort
    og et nytt forsøk møter «nothing to commit».

    Begge sider normaliseres likt, så sammenligningen ikke hviler på at vi har
    gjettet nøyaktig samme brettingsregel som git.
    """
    first = re.split(r"\n\s*\n", message.strip(), maxsplit=1)[0]
    return " ".join(first.split())


class LandingRefused(RuntimeError):
    """Landingen ble ikke gjort, eller ble gjort men holdt ikke etterkontrollen.

    Bærer ``commit`` når en commit faktisk kan finnes, slik at et menneske kan
    gå og se på den. Vi rydder den ikke bort selv — se modul-docstringen.
    """

    def __init__(self, reasons: Sequence[str], *, commit: str = "") -> None:
        self.reasons = tuple(reasons)
        self.commit = commit
        super().__init__("; ".join(self.reasons) or "landing refused")


@dataclass(frozen=True)
class LandingSnapshot:
    """Det som var sant like før staging. Se modul-docstring: evidens, ikke vern."""

    head: str
    tracked: tuple[str, ...]
    staged: tuple[str, ...]
    worktree_blobs: Mapping[str, str]

    def foreign_staged(self, declared: Sequence[str]) -> tuple[str, ...]:
        """Stagede stier som IKKE er våre — det ``--only`` skal la være i fred."""
        mine = set(declared)
        return tuple(sorted(p for p in self.staged if p not in mine))


@dataclass(frozen=True)
class LandingResult:
    ok: bool
    commit: str
    declared: tuple[str, ...]
    committed: tuple[str, ...] = ()
    foreign: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    foreign_staged_before: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()

    def summary(self) -> str:
        """Én linje om hva som faktisk skjedde, ikke hva som var meningen."""
        if not self.ok:
            head = f"landing refused (commit may exist: {self.commit[:12]})" if self.commit else "landing refused"
            return f"{head}: " + "; ".join(self.reasons)
        return (
            f"landed {self.commit[:12]}: {len(self.committed)} file(s) == declared set, "
            f"0 foreign (index held {len(self.foreign_staged_before)} foreign staged "
            f"path(s), left untouched)"
        )


def _split_z(path: Path) -> tuple[str, ...]:
    try:
        raw = path.read_bytes().decode("utf-8", errors="surrogateescape")
    except OSError:
        return ()
    return tuple(part for part in raw.split("\0") if part)


def _first_line(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8", errors="surrogateescape").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


class GitLandingExecutor:
    """Stage nøyaktig landingssettet, commit, og les tilbake hva som landet."""

    def __init__(
        self,
        repo: str | os.PathLike[str] | None = None,
        *,
        record_path: str | os.PathLike[str] | None = None,
        timeout: int = 120,
    ) -> None:
        self.repo = Path(repo or REPO_ROOT)
        self.record_path = Path(record_path) if record_path else None
        self.timeout = timeout

    # -- offentlig ---------------------------------------------------------

    def land(self, landing_set: Sequence[str], message: str) -> LandingResult:
        """Utfør landingen. Returnerer ALLTID et resultat; kaster aldri.

        Et avslag er et måleresultat på linje med en vellykket landing, og skal
        kunne leses uten å fanges. :func:`landing_callable` er den som gjør et
        avslag til en exception, fordi runneren trenger det som en blokkering.

        At den heller ikke kaster på en TIDSAVBRUTT git er en rettelse: et
        tidligere utkast lot ``TimeoutExpired`` gå rett gjennom, og da mistet
        den commiten som git rakk å lage før avbruddet — nøyaktig den
        foreldreløse commiten ``LandingRefused.commit`` finnes for å navngi.
        """
        declared, reasons = self._normalise(landing_set)
        text = str(message or "").strip()
        if not text:
            reasons = (*reasons, "commit message is empty — a landing with no stated reason is not reviewable")
        if reasons:
            return LandingResult(False, "", declared, reasons=reasons)

        try:
            return self._land(declared, text)
        except (subprocess.SubprocessError, OSError) as exc:
            # git kan ha rukket å lage commiten før avbruddet. Målt: en
            # post-commit-hook som sover forbi tidsavbruddet gir nettopp det.
            return LandingResult(
                False, self._head(), declared,
                reasons=(
                    f"git did not report back ({type(exc).__name__}: {exc}); a commit MAY "
                    f"exist — inspect the named SHA before retrying, since a retry will "
                    f"otherwise meet 'nothing to commit'",
                ),
            )

    # -- trinn -------------------------------------------------------------

    def _land(self, declared: tuple[str, ...], text: str) -> LandingResult:
        snapshot = self._snapshot(declared)
        foreign_staged = snapshot.foreign_staged(declared)

        pre = self._pre_checks(declared, snapshot)
        if pre:
            return LandingResult(False, "", declared, reasons=pre, foreign_staged_before=foreign_staged)

        added, stage_error = self._stage(declared, snapshot)
        if stage_error:
            self._undo_our_intent_to_add(added)
            return LandingResult(False, "", declared, reasons=(stage_error,), foreign_staged_before=foreign_staged)

        ok, sha, output = self._commit(declared, text)
        if not ok:
            self._undo_our_intent_to_add(added)
            return LandingResult(
                False, "", declared,
                reasons=(f"git commit --only refused the landing set: {output}",),
                foreign_staged_before=foreign_staged,
            )

        result = self._verify(declared, snapshot, sha, _subject_of(text))
        self._record(result, text)
        return result

    def _normalise(self, landing_set: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Avvis alt som ikke er én navngitt, repo-relativ, normalisert fil.

        Hvert avslag her er en målt farekilde, ikke en smaksdom — se de enkelte
        begrunnelsene.
        """
        seen: list[str] = []
        for raw in landing_set or ():
            path = str(raw).strip()
            if path and path not in seen:
                seen.append(path)
        if not seen:
            # Samme regel som LandingScopeGate: fravær av data er ikke et
            # positivt funn. Et tomt sett er UKJENT, ikke «ingen filer».
            return (), (
                "landing set is empty or unknown — a commit whose file set is not "
                "known cannot be staged, and an unknown set is not an empty one",
            )

        reasons: list[str] = []
        root = self.repo.resolve()
        for path in seen:
            if any(ch in path for ch in _FORBIDDEN_CHARS):
                reasons.append(
                    f"path holds a glob or control character, which git would expand "
                    f"past the set the gate judged: {path!r}")
                continue
            if path.startswith(":"):
                reasons.append(f"path uses git pathspec magic and names no single file: {path!r}")
                continue
            if os.path.isabs(path):
                reasons.append(
                    f"path is absolute; the lease, the gate and the commit all speak "
                    f"repo-relative paths: {path!r}")
                continue
            if ".." in PurePosixPath(path).parts:
                reasons.append(f"path climbs out of the repository: {path!r}")
                continue
            if str(PurePosixPath(path)) != path:
                # './mine.py' og 'a//b.py' er lovlige for git, men git skriver dem
                # om til 'mine.py' og 'a/b.py' i tilbakelesingen. Etterkontrollen
                # sammenligner strenger, så en uNORMALISERT stavemåte ville gitt
                # falsk «fremmed fil» + «landet ikke» på en helt riktig commit —
                # og commiten er allerede gjort, så en retry møter «nothing to
                # commit». Krev stavemåten git selv ville brukt.
                reasons.append(
                    f"path is not in the spelling git reads back "
                    f"({str(PurePosixPath(path))!r}), so the readback could not match it: {path!r}")
                continue
            try:
                resolved = (self.repo / path).resolve()
            except OSError as exc:  # pragma: no cover - filsystemfeil
                reasons.append(f"path is unreadable: {path!r} ({exc})")
                continue
            if resolved != root and root not in resolved.parents:
                reasons.append(f"path resolves outside the repository: {path!r}")
                continue
            if resolved.is_dir():
                # Målt: `git commit --only -- d` lander HVER fil under d. Vakten
                # ville da dømt én oppføring mens N filer landet.
                reasons.append(
                    f"path is a directory; git expands it to every file beneath it, so "
                    f"the gate would judge one entry while many files land: {path!r}")
        return tuple(seen), tuple(reasons)

    def _shell(self, script: str, args: Sequence[str], reader: Callable[[Path], object]) -> object:
        """Kjør ett skall som legger utdata i FILER, ikke i en avgrenset strøm.

        Markørbaserte seksjoner i én stdout kan forveksles med innhold: et
        filnavn som er ``@@END@@`` er nok. Egne filer per seksjon gjør den
        forvekslingen umulig, og lar hver liste være NUL-separert.
        """
        with tempfile.TemporaryDirectory(prefix="faber-landing-") as tmp:
            proc = subprocess.run(
                ["sh", "-c", script, "sh", tmp, *args],
                cwd=str(self.repo), capture_output=True, text=True, timeout=self.timeout,
            )
            return reader(Path(tmp)), proc.returncode  # type: ignore[return-value]

    def _head(self) -> str:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(self.repo),
                capture_output=True, text=True, timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return ""
        return proc.stdout.strip() if proc.returncode == 0 else ""

    def _snapshot(self, declared: Sequence[str]) -> LandingSnapshot:
        """Les indeks, sporingsstatus og arbeidstre-innhold i ÉN prosess.

        Kravet er å lese ``git ls-files`` og ``git diff --cached --name-only`` i
        SAMME steg: to separate kall har et vindu der en parallell strøm rekker
        å legge noe i den delte indeksen mellom dem.
        """
        def read(tmp: Path) -> LandingSnapshot:
            pairs = _split_z(tmp / "blobs")
            blobs = dict(zip(pairs[0::2], pairs[1::2]))
            return LandingSnapshot(
                head=_first_line(tmp / "head"),
                tracked=_split_z(tmp / "tracked"),
                staged=_split_z(tmp / "staged"),
                worktree_blobs=blobs,
            )

        snapshot, _ = self._shell(_SNAPSHOT_SCRIPT, declared, read)  # type: ignore[misc]
        return snapshot  # type: ignore[return-value]

    def _pre_checks(self, declared: Sequence[str], snapshot: LandingSnapshot) -> tuple[str, ...]:
        tracked = set(snapshot.tracked)
        reasons: list[str] = []
        for path in declared:
            blob = snapshot.worktree_blobs.get(path, "ABSENT")
            if blob == "ABSENT" and path not in tracked:
                reasons.append(
                    f"declared path is neither tracked nor present in the worktree, so "
                    f"there is nothing for the landing to carry: {path!r}")
            elif blob == "UNREADABLE":
                reasons.append(f"declared path could not be hashed, so its landing cannot be verified: {path!r}")
        return tuple(reasons)

    def _stage(self, declared: Sequence[str], snapshot: LandingSnapshot) -> tuple[tuple[str, ...], str]:
        """``git add -N`` — kun for de git ennå ikke kjenner.

        ``--only`` ser bort fra alt som ikke er sporet, så en ny fil trenger en
        intent-to-add-oppføring for i det hele tatt å kunne landes. Sporede
        stier røres ikke: hvert unødvendig skriv til den delte indeksen er en
        sjanse til å forstyrre en parallell strøm.

        Returkoden leses. En låst indeks gir ellers «pathspec did not match any
        files» videre nedstrøms — et ærlig utfall med feil diagnose.
        """
        tracked = set(snapshot.tracked)
        untracked = tuple(p for p in declared if p not in tracked)
        if not untracked:
            return (), ""
        proc = subprocess.run(
            ["git", "add", "-N", "--", *untracked],
            cwd=str(self.repo), capture_output=True, text=True, timeout=self.timeout,
        )
        if proc.returncode != 0:
            return (), (
                "git add -N could not record the new files, so the landing was never "
                f"staged: {(proc.stderr or proc.stdout).strip()}")
        return untracked, ""

    def _undo_our_intent_to_add(self, added: Sequence[str]) -> None:
        """Rydd bort VÅRE intent-to-add-oppføringer etter en feilet landing.

        En feilet commit etterlater ellers ``A <fil>`` i den DELTE indeksen for
        alltid — og da ville en parallell strøms ``git commit -a`` sveipet
        nettopp den fila. Modulen ville brutt sitt eget prinsipp én etasje ned.

        Målt: ``git reset -- <sti>`` på en sti en annen strøm har staget med ekte
        innhold kaster det innholdet. Så vi må vite hvilke oppføringer som er
        VÅRE, og det finnes en eksakt måling: en ren intent-to-add vises IKKE i
        ``git diff --cached --name-only``, mens alt som er staget med innhold
        gjør det. Siden vi kun la til stier som var USPORET, betyr «ikke i
        diff --cached» nøyaktig «fortsatt bare vår intent-to-add».

        Et mellomutkast sjekket i tillegg at bloben var den tomme. Det er en
        heuristikk for det samme faktumet — en annen strøm kan ha staget en
        genuint tom fil — og etter at målingen over kom inn, kunne ingen test
        lenger skille de to sjekkene fra hverandre. En vakt ingen test kan drepe,
        beviser ingenting; den er fjernet framfor å stå som pynt.
        """
        if not added:
            return

        def read(tmp: Path) -> tuple[str, ...]:
            really_staged = set(_split_z(tmp / "staged"))
            return tuple(path for path in added if path not in really_staged)

        try:
            still_ours, _ = self._shell(_INDEX_STATE_SCRIPT, added, read)  # type: ignore[misc]
            if still_ours:
                subprocess.run(
                    ["git", "reset", "-q", "--", *still_ours],
                    cwd=str(self.repo), capture_output=True, text=True, timeout=self.timeout,
                )
        except (subprocess.SubprocessError, OSError):
            return

    def _commit(self, declared: Sequence[str], message: str) -> tuple[bool, str, str]:
        """``git commit --only -- <stier>``, og les SHA-en i SAMME prosess.

        Aldri ``-a``, aldri uten stier. SHA-en må komme herfra og ikke fra et
        senere ``git rev-parse HEAD``: på et delt arbeidstre kan HEAD ha flyttet
        seg til en annen strøms commit innen vi rekker å spørre.
        """
        def read(tmp: Path) -> tuple[str, str]:
            out = tmp / "out"
            said = out.read_text(encoding="utf-8", errors="replace").strip() if out.exists() else ""
            return _first_line(tmp / "sha"), said

        (sha, output), code = self._shell(_COMMIT_SCRIPT, [message, *declared], read)  # type: ignore[misc]
        return code == 0 and bool(sha), sha, output

    def _verify(
        self,
        declared: Sequence[str],
        snapshot: LandingSnapshot,
        sha: str,
        subject: str,
    ) -> LandingResult:
        """Les VÅR commit tilbake fra git og krev at den er nøyaktig den avtalte."""
        def read(tmp: Path) -> tuple[str, str, tuple[str, ...], dict[str, str]]:
            pairs = _split_z(tmp / "blobs")
            return (
                _first_line(tmp / "parent"),
                _first_line(tmp / "subject"),
                tuple(sorted(_split_z(tmp / "files"))),
                dict(zip(pairs[0::2], pairs[1::2])),
            )

        (parent, landed_subject, committed, head_blobs), _ = self._shell(  # type: ignore[misc]
            _VERIFY_SCRIPT, [sha, *declared], read)

        wanted = set(declared)
        foreign = tuple(sorted(set(committed) - wanted))
        missing = tuple(sorted(wanted - set(committed)))
        reasons: list[str] = []
        observations: list[str] = []

        if not sha:
            reasons.append("the commit SHA could not be read back")
        landed_subject = " ".join(landed_subject.split())
        if subject and landed_subject and landed_subject != subject:
            # Ville fanget en forvekslet commit selv om SHA-en var lest feil.
            # `subject` er allerede normalisert av `_subject_of`; git-siden
            # normaliseres her, slik at sammenligningen ikke hviler på at vi har
            # gjettet nøyaktig samme brettingsregel som git.
            reasons.append(
                f"the verified commit is not the one this landing wrote "
                f"(subject {landed_subject!r} != {subject!r})")

        # Kravet ordrett: antall filer i commiten == landingssettet, og 0 fremmede.
        if len(committed) != len(wanted):
            reasons.append(
                f"commit holds {len(committed)} file(s) but the declared landing set "
                f"holds {len(wanted)}")
        if foreign:
            reasons.append(
                "commit carries files outside the declared landing set: "
                + ", ".join(foreign[:10])
                + (f" (+{len(foreign) - 10} more)" if len(foreign) > 10 else ""))
        if missing:
            # Også en feil: vakten dømte deklarasjonen, så en deklarert fil som
            # ikke landet gjør evidensen usann selv om ingenting fremmed kom med.
            reasons.append(
                "declared files did not land, so the approved set was not what was "
                "committed: " + ", ".join(missing[:10]))

        for path in declared:
            before = snapshot.worktree_blobs.get(path, "ABSENT")
            after = head_blobs.get(path, "ABSENT")
            if before == "ABSENT":
                if after != "ABSENT":
                    reasons.append(f"path was absent before the landing but exists in the commit: {path!r}")
            elif after == "ABSENT":
                reasons.append(f"declared path is missing from the commit tree: {path!r}")
            elif after != before:
                # Innholdet endret seg mellom før-målingen og commiten: noen skrev
                # i fila under oss. Filsettet kan være riktig og innholdet likevel
                # ikke være det som ble reviewet.
                reasons.append(
                    f"content changed between the pre-stage reading and the commit "
                    f"({before[:12]} -> {after[:12]}); the landed bytes are not the "
                    f"bytes that were measured: {path!r}")

        if snapshot.head and parent and parent != snapshot.head:
            observations.append(
                f"another commit landed between the reading and this one "
                f"(expected parent {snapshot.head[:12]}, got {parent[:12]}); this "
                f"landing's own file set is still exactly as declared")

        return LandingResult(
            ok=not reasons,
            commit=sha,
            declared=tuple(declared),
            committed=committed,
            foreign=foreign,
            missing=missing,
            foreign_staged_before=snapshot.foreign_staged(declared),
            reasons=tuple(reasons),
            observations=tuple(observations),
        )

    def _record(self, result: LandingResult, message: str) -> None:
        """Skriv etterkontrollen ned. Feiler stille — et tapt notat skal aldri
        endre utfallet av en landing som allerede er gjort."""
        target = self.record_path or (faber_home() / "landings.jsonl")
        record = {
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repo": str(self.repo),
            "subject": message.splitlines()[0] if message else "",
            "ok": result.ok,
            "commit": result.commit,
            "declared": list(result.declared),
            "committed": list(result.committed),
            "foreign": list(result.foreign),
            "missing": list(result.missing),
            "foreign_staged_before": list(result.foreign_staged_before),
            "reasons": list(result.reasons),
            "observations": list(result.observations),
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            return


def landing_callable(
    *,
    message: str,
    prelanding: LandingEvidence,
    repo: str | os.PathLike[str] | None = None,
    executor: GitLandingExecutor | None = None,
) -> Callable[[Mapping[str, str]], LandingEvidence]:
    """Bygg ``landing``-callbacken :class:`GovernedCodeRunner` faktisk kaller.

    Settet utledes fra ``prelanding.landing_set`` og kan ikke oppgis separat.
    Det er den samme verdien :class:`~agent.code_workflow.LandingScopeGate` måler
    mot leasen inne i runneren, så hånden kan ikke lande noe annet enn det vakten
    dømte. Se modul-docstringen for hvorfor et separat argument ble fjernet: med
    to innganger landet en uleaset fil, og målet gikk til LANDED.

    Evidensen som returneres bærer den MÅLTE commiten og det MÅLTE filsettet,
    ikke de deklarerte. Er de to forskjellige, kommer vi ikke hit: da kaster vi,
    og runneren blokkerer målet.
    """
    runner = executor or GitLandingExecutor(repo)
    declared = tuple(str(p).strip() for p in prelanding.landing_set if str(p).strip())

    def _land(_build_evidence: Mapping[str, str]) -> LandingEvidence:
        result = runner.land(declared, message)
        if not result.ok:
            raise LandingRefused(result.reasons, commit=result.commit)
        return replace(prelanding, commit=result.commit, landing_set=result.committed)

    return _land
