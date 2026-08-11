"""faber_implementer.py — steg 8 (``faber_implementation``): utfoereren, ikke stubben.

BL-4050. Vakten for dette steget landet i BL-4029 (``be9141f18``): ``ScopeBudget``
evalueres i :class:`~agent.code_workflow.GovernedCodeRunner` rett etter ``build()``.
Men det ``build()`` faktisk var, paa den ene stien som kjoerer, var::

    agent/faber_runtime.py:153   build=lambda: payload["build"]

Altsaa: kjeden leste blast-radiusen sin ut av det samme JSON-objektet som ba den om
aa kjoere. Vakten var ekte, men den maalte en tallverdi som avsenderen hadde skrevet
selv. **Det er ikke en maaling, det er et sitat.** Denne modulen erstatter sitatet
med en maaling.

## Den ene regelen alt annet henger paa

**Maaletallene kommer fra bytes paa disk, aldri fra modellen.**

En LLM som blir spurt «hvor mange linjer endret du?» rett etter aa ha blitt fortalt
«budsjettet er 500 linjer» svarer 480. Ikke av ondskap — den moenstermatcher mot en
oppgave som ser ut som «hold deg under grensen». Aa la generatoren fylle inn sitt
eget maaletall ville gjenskapt stubben med flere trinn: kjeden ville fortsatt lest
et tall den ble gitt.

Derfor: generatoren produserer INNHOLD. :func:`measure_blast_radius` produserer
TALLENE, ved aa diffe det som ble skrevet mot det som stod der foer. Hvis modellen
likevel oppgir tall (den blir bedt om aa la vaere), blir de bevart som
``model_claimed_*`` og sammenlignet — et avvik er BEVIS, ikke en overstyring.

## Hvorfor maalingen skjer FOER skrivingen

Runneren evaluerer budsjettet etter at ``build()`` har returnert. Hadde vi skrevet
foerst, ville en blokkert build etterlatt treet skittent — og neste ticks steg 4
(``git_clean``) ville feilet paa vaart eget rot, som en autonom loop ikke kommer ut
av selv.

Saa: forslaget maales mot pre-imagene FOER noe skrives. Er det utenfor budsjett,
skrives ingenting — og de **ekte, for store tallene rapporteres likevel**. Utfoereren
krymper aldri sitt eget tall for aa slippe forbi sin egen vakt; den lar vakten
fyre. Se :func:`FaberImplementer.build`.

## Sekvensen

1. les designet fra steg 7 (:class:`DesignStore`) — mangler det, er dette et gjett,
   ikke en implementasjon
2. les pre-imagene av lease-settet (samme lesning som mates til modellen, saa
   diff-basen ER det modellen saa)
3. kall cortex → fulle filinnhold (ikke diff: en diff som ikke lar seg applisere
   halv-applisers stille, og en halv-applisert patch er verre enn ingen)
4. avvis forslaget hvis det er tomt, uendret, utenfor leasen, ikke-parsbart, eller
   inneholder kreditiv-formet materiale
5. MAAL blast-radiusen mot pre-imagene
6. utenfor budsjett → skriv ingenting, kast med de EKTE tallene
7. innenfor → skriv atomisk, kjoer de navngitte testene, rull tilbake hvis de
   feiler

## Skarpe kanter i kontrakten oppstroems (maalt, ikke antatt)

* Runneren sjekker ``tests`` FOER ``changed_files``/``changed_lines``. En aerlig
  scope-avvisning har ingen testevidens — ingenting ble skrevet, saa ingenting ble
  testet — og ville derfor blitt rapportert som «build returned no test evidence»,
  som skjuler aarsaken. Aa syntetisere en ``tests``-streng for aa styre hvilken gate
  som fyrer ville vaert nettopp det BL-3673 blokkerte. Loesningen er ingen av
  delene: avvisningen KASTES, saa AARSAKSTEKSTEN overlever i maalets ``blocker`` og
  i journalen. Vaer presis om hva som IKKE overlever: runnerens ytre haandterer
  beholder bare ``str(exc)``, saa ``ImplementationBlocked.evidence`` og ``gate``
  forkastes av den. Tallene naar ikke journalen — teksten gjoer. Aa la dem overleve
  er en endring i runneren, ikke her.
* Runneren godtar en hvilken som helst ikke-tom ``tests``-verdi. ``"FAILED: 3"`` er
  ikke-tom. Denne modulen setter derfor ``tests`` **kun** naar testene er groenne.

## Ett budsjett, ikke to

Utfoereren kjenner budsjettet for aa kunne LA VAERE aa skrive — ikke for aa kunne
pynte paa tallet. Men to eksemplarer av en grense er to grenser som kan vaere uenige;
det er to-verdener-defekten fra BL-4029 L6 i det smaa. Bruk derfor
:meth:`FaberImplementer.bound_to`, som binder utfoereren til runnerens EGET
budsjettobjekt.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from agent.code_workflow import ScopeBudget, SecretPolicy

#: Kreditiv-former som ikke gir falske positive paa vanlig kildekode.
#:
#: Bevisst IKKE hele :class:`~agent.code_workflow.SecretPolicy` her. Dens
#: noekkelord-moenstre treffer ``token = parse(x)`` og ``password: str`` — helt
#: alminnelig Python — og en gate som blokkerer legitimt arbeid hver gang blir
#: skrudd av. En avskrudd gate er modulens egen laerdom, ett hakk verre: en
#: kontroll som ikke kan fyre er ikke en kontroll. Full SecretPolicy brukes
#: fortsatt paa evidensen vi persisterer, der den er presis.
#: Ankeret er ``(?<![A-Za-z0-9])``, ikke ``\b``. MAALT: ``\b`` fyrer IKKE paa
#: ``leak_sk-ABCDEFGHIJKLMNOPQRSTUVWX.py``, fordi ``_`` er et ordtegn og det derfor
#: ikke finnes noen ordgrense mellom ``_`` og ``s``. Et prefiks er alt som skal til
#: for aa gaa forbi — og modellen styrer filnavnene den foreslaar. Lookbehinden
#: krever bare at tegnet foran ikke er alfanumerisk, saa understrek, punktum og
#: skraastrek slipper moensteret til.
_CREDENTIAL_SHAPES = (
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![0-9A-Z])"),
    re.compile(r"(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    # BLOKKEN, ikke bare hodet. Et hode-moenster oppdager en noekkel korrekt, men
    # etterlater selve noekkelmaterialet naar treffet erstattes span-vis — detektoren
    # og redigereren var uenige om hva funnet BESTOD i. `|$`-alternativet er
    # loefteboerende: uten det slutter en AVKORTET noekkel aa bli oppdaget i det hele
    # tatt, som er en daarligere byttehandel enn den var ment aa loese.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
               r"(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
)

_DEFAULT_CORTEX_URL = "http://192.168.40.13:1234/v1"

_REDACTED = "(redacted)"


def _redact(text: str) -> str:
    """Rens FRITEKST — modellens begrunnelse, testutdata, aarsakstekster.

    Her brukes hele :class:`SecretPolicy`, inkludert noekkelord-moenstrene som
    bevisst IKKE brukes paa filinnhold. Forskjellen er hva en falsk positiv koster:
    paa kildekode ville den blokkert legitimt arbeid, saa gaten ville blitt skrudd
    av. Paa fritekst koster den noen ord.

    **BARE TREFFET ERSTATTES, ikke hele strengen.** Foerste versjon byttet ut hele
    teksten, og MAALT paa realistisk avvisningsprosa var det 5 av 5 falske positive:
    en begrunnelse som «the design needs api_key= wired through, but config.py is not
    in the lease» ble til bare «(redacted)». Da runnerens ytre haandterer i tillegg
    forkaster ``gate``, satt maalet igjen med en blocker uten ETT handlingsbart ord —
    ikke hvilken gate, ikke at det var en tom patch, ikke hvorfor.

    Det er BL-4029-defekten («journalen lagret feil aarsak») gjeninnfoert av rettelsen
    for en annen. En autonom loop som faar en ugjennomsiktig blocker proever igjen i
    blinde. Selve BESLUTNINGEN om aa redigere er uendret — bare omfanget av
    erstatningen — saa eksponeringen er den samme, og resten av setningen overlever.
    """
    value = str(text or "")
    if not value.strip():
        return value
    # REKKEFOELGEN ER LOEFTEBOERENDE: formene foerst. SecretPolicy har sitt EGET
    # hode-bare-PEM-moenster, saa kjoerer den foerst spiser den `BEGIN`-markoeren, og
    # blokk-matcheren under finner ingenting igjen aa ta — noekkelen blir staaende.
    for shape in _CREDENTIAL_SHAPES:
        value = shape.sub(_REDACTED, value)
    for pattern in SecretPolicy.violations(value):
        # violations() gir moensterstrengen; `(?i)` staar inline i den og overlever.
        value = re.sub(pattern, _REDACTED, value)
    return value


class ImplementationBlocked(RuntimeError):
    """Steg 8 nekter aa produsere en endring, med maskinlesbar aarsak.

    ``gate`` navngir hvilken gate som EGENTLIG holder, selv naar runneren
    rapporterer en annen paa grunn av rekkefoelgen i sjekkene sine.

    INVARIANT SOM MAA HOLDES: alt som kan baere modellstyrt tekst kastes som
    NETTOPP denne typen. Redigeringen under er derfor uttoemmende i dag, men den er
    det ved konstruksjon bare saa lenge invarianten holder — legger noen til et
    `raise` av en annen type med modelltekst i meldingen, gaar den utenom. (Maalt:
    to unntak slipper raa forbi i dag, `UnicodeEncodeError` fra `diff_id_for` og
    `UnicodeDecodeError` fra `read_pre_images`; begge baerer bare kodepunkt og
    posisjon, ingen innhold.)
    """

    def __init__(self, reason: str, *, gate: str = "implementation",
                 evidence: Mapping[str, Any] | None = None):
        # AARSAKSTEKSTEN REDIGERES HER, i flaskehalsen — ikke paa hvert kallested.
        #
        # Flere av avvisningene siterer modellstyrt tekst (begrunnelsen ved tom
        # patch, filnavn ved lease-brudd og ved duplikat). Aa rense dem én og én
        # lukker de kallestedene som finnes i dag og aapner klassen igjen ved neste
        # `raise` noen legger til.
        #
        # Og dette er kanalen som faktisk overlever: runnerens ytre haandterer
        # (`code_workflow.py`, `except Exception`) beholder BARE ``str(exc)`` og
        # forkaster baade ``evidence`` og ``gate``. Vakten laa altsaa paa kanalen
        # som blir kastet, mens den som havner i maalets ``blocker`` og i journalen
        # sto uten. Rediger FOER avkorting, ellers kan et kutt midt i et moenster
        # gjoere det ugjenkjennelig for filteret og lesbart for et menneske.
        reason = _redact(reason)
        super().__init__(reason)
        self.reason = reason
        self.gate = gate
        #: Maalt evidens paa avvisningstidspunktet, naar det finnes. En avvisning
        #: uten tallene den bygger paa kan ikke etterproeves.
        self.evidence: Mapping[str, Any] = dict(evidence or {})


# --------------------------------------------------------------- steg 7 → 8 ---


@dataclass(frozen=True)
class DesignRecord:
    """Det steg 7 (``sol_design_review_pass``) etterlater til steg 8.

    ``tests`` er ikke valgfritt. Et design som ikke navngir en test som beviser
    endringen, kan ikke produsere testevidens — og en build uten testevidens
    blokkeres uansett ett steg senere. Aa oppdage det her gir en presis grunn i
    stedet for en generisk.
    """

    goal_id: str
    design: str
    target_files: tuple[str, ...]
    tests: tuple[str, ...]
    acceptance: str = ""
    cad_ref: str = ""
    adr_ref: str = ""
    bl_ref: str = ""

    def assert_actionable(self) -> None:
        missing = [
            name
            for name, value in (
                ("design", self.design.strip()),
                ("target_files", self.target_files),
                ("tests", self.tests),
            )
            if not value
        ]
        if missing:
            raise ImplementationBlocked(
                "design from step 7 is not actionable, missing: " + ", ".join(missing),
                gate="design_gate",
            )


class DesignStore:
    """Der steg 7 legger designet og steg 8 henter det.

    Fravaer er BLOCK, ikke «ingen krav». Et manglende design betyr at steg 7 ikke
    har kjoert for dette maalet — og en implementasjon uten design er et gjett med
    skrivetilgang.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None):
        base = root or (
            Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes-gui")))
            / "faber"
            / "designs"
        )
        self.root = Path(base).expanduser()

    def path_for(self, goal_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(goal_id).strip())
        if not safe:
            raise ImplementationBlocked("design lookup needs a goal id", gate="design_gate")
        return self.root / f"{safe}.json"

    def save(self, record: DesignRecord) -> Path:
        path = self.path_for(record.goal_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "goal_id": record.goal_id,
            "design": record.design,
            "target_files": list(record.target_files),
            "tests": list(record.tests),
            "acceptance": record.acceptance,
            "cad_ref": record.cad_ref,
            "adr_ref": record.adr_ref,
            "bl_ref": record.bl_ref,
        }
        SecretPolicy.assert_safe_payload(payload)
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return path

    def load(self, goal_id: str) -> DesignRecord:
        path = self.path_for(goal_id)
        if not path.exists():
            raise ImplementationBlocked(
                f"no step-7 design for {goal_id} at {path} — an implementation "
                "without a design is a guess with write access",
                gate="design_gate",
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImplementationBlocked(
                f"step-7 design unreadable at {path}: {exc}", gate="design_gate"
            ) from exc
        if not isinstance(payload, Mapping):
            raise ImplementationBlocked(
                f"step-7 design malformed at {path}: expected an object", gate="design_gate"
            )
        record = DesignRecord(
            goal_id=str(payload.get("goal_id") or goal_id),
            design=str(payload.get("design") or ""),
            target_files=tuple(str(p) for p in (payload.get("target_files") or ())),
            tests=tuple(str(p) for p in (payload.get("tests") or ())),
            acceptance=str(payload.get("acceptance") or ""),
            cad_ref=str(payload.get("cad_ref") or ""),
            adr_ref=str(payload.get("adr_ref") or ""),
            bl_ref=str(payload.get("bl_ref") or ""),
        )
        record.assert_actionable()
        return record


# ------------------------------------------------------------ blast-radius ---


@dataclass(frozen=True)
class BlastRadius:
    """Maalt endringsomfang. Utledet fra bytes, aldri oppgitt av en generator.

    ``changed_lines`` er CHURN — ``added + deleted`` — ikke bare tillegg.
    Konvensjonen staar her fordi den er nettopp der underrapportering gjemmer seg:
    med «bare tillegg» ville en ren sletting av 300 linjer maalt 0 endrede linjer og
    passert et 500-linjers budsjett som en null-endring. ``deleted_lines``
    rapporteres i tillegg, siden :class:`~agent.code_workflow.ScopeBudget` har en
    egen, lavere grense for det.
    """

    changed_files: int
    changed_lines: int
    added_lines: int
    deleted_lines: int
    new_dependencies: int
    per_file: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()

    def as_evidence(self) -> dict[str, int]:
        return {
            "changed_files": self.changed_files,
            "changed_lines": self.changed_lines,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "new_dependencies": self.new_dependencies,
        }


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _line_delta(before: str, after: str) -> tuple[int, int]:
    """(lagt til, slettet) mellom to filinnhold, etter samme regnskap som ``git --numstat``."""
    import difflib

    added = deleted = 0
    for line in difflib.unified_diff(_lines(before), _lines(after), lineterm="", n=0):
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def _top_level_imports(source: str) -> set[str]:
    """Toppnivaa-modulnavn som *source* importerer, eller tom mengde hvis den ikke parser.

    KJENT GRENSE, skrevet ned her fordi maalingen gaar mot en hard grense paa null:
    dette ser ``import x`` og ``from x import y`` hvor som helst i fila, ogsaa inne i
    funksjonskropper — men IKKE ``importlib.import_module("x")`` eller
    ``__import__("x")``. En slik avhengighet maales som 0 og passerer
    ``max_new_dependencies=0``. Grensen er ikke-adversariell (en generator som ville
    smugle inn en avhengighet ville hatt lettere veier), men les aldri 0 herfra som
    «ingen» — les det som «ingen statiske».
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def measure_blast_radius(
    pre: Mapping[str, str | None],
    post: Mapping[str, str],
    *,
    repo_root: Path | None = None,
) -> BlastRadius:
    """Maal *post* mot *pre*. ``pre[path] is None`` betyr «filen fantes ikke».

    Kalles med det som faktisk skal skrives, foer det skrives — og med akkurat de
    pre-imagene generatoren fikk se, saa diff-basen ikke kan ha flyttet seg under
    kallet.
    """
    per_file: dict[str, tuple[int, int]] = {}
    added_total = deleted_total = 0
    changed_files = 0
    new_deps: set[str] = set()
    for path, new_content in post.items():
        old_content = pre.get(path)
        base = "" if old_content is None else old_content
        if base == new_content:
            per_file[path] = (0, 0)
            continue
        added, deleted = _line_delta(base, new_content)
        per_file[path] = (added, deleted)
        added_total += added
        deleted_total += deleted
        changed_files += 1
        if path.endswith(".py"):
            new_deps |= _top_level_imports(new_content) - _top_level_imports(base)
    external = tuple(sorted(_external_dependencies(new_deps, repo_root)))
    return BlastRadius(
        changed_files=changed_files,
        changed_lines=added_total + deleted_total,
        added_lines=added_total,
        deleted_lines=deleted_total,
        new_dependencies=len(external),
        per_file=per_file,
        dependencies=external,
    )


def _external_dependencies(names: set[str], repo_root: Path | None) -> set[str]:
    """Trekk fra stdlib og alt som ligger i repoet selv.

    Foerstepartsnavn bestemmes ved aa se etter modulen paa disk, ikke ved en
    hardkodet liste: en liste blir foreldet stille, og et nytt internt navn ville
    da telt som en ny ekstern avhengighet og blokkert paa null-grensen.
    """
    external = {n for n in names if n and n not in sys.stdlib_module_names}
    if repo_root is None:
        return external
    return {
        n
        for n in external
        if not (repo_root / n).is_dir() and not (repo_root / f"{n}.py").exists()
    }


# ------------------------------------------------------------- generatoren ---


@dataclass(frozen=True)
class ProposedPatch:
    """Generatorens produkt: innhold, og hva den eventuelt paastod om seg selv."""

    files: Mapping[str, str]
    rationale: str = ""
    model_claimed: Mapping[str, Any] = field(default_factory=dict)
    model_id: str = ""


_SYSTEM_PROMPT = """You are Faber, the implementation step of a governed autocoder chain.

You write code. You do NOT report how much you changed: the chain measures that from
the bytes you return, and a number you supply is ignored. Optimising your answer to
look small changes nothing except making your answer wrong.

Rules, all enforced mechanically after you answer:
- You may only write files from the allowed list. Any other path voids the whole patch.
- Return the COMPLETE new content of every file you touch. Not a diff, not an excerpt,
  not an elision like "# ... rest unchanged". The content you return replaces the file.
- Python you return must parse. A file that does not parse voids the whole patch.
- If the design cannot be implemented within the allowed files, return an empty file
  list and say why in "rationale". That is a legitimate, useful answer.

Answer with a single JSON object and nothing else:
{"files": [{"path": "<allowed path>", "content": "<complete file content>"}],
 "rationale": "<why this implements the design, and any risk you see>"}"""


class CortexPatchGenerator:
    """Kaller cortex paa .13 og returnerer et forslag. Ingen sideeffekter.

    Modell-id-en resolves LIVE — ingen hardkodet id noe sted. Vi gjenbruker
    ``continuous_pipeline.default_live_model_resolver`` framfor aa duplisere en
    resolver, saa det finnes ett sted som bestemmer hvilken modell rollen peker paa.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        role: str = "builder_671b",
        timeout: float = 900.0,
        temperature: float = 0.1,
        transport: Callable[[str, Mapping[str, Any], float], Mapping[str, Any]] | None = None,
    ):
        self.base_url = (base_url or os.environ.get("OPUS_REASONER_URL", _DEFAULT_CORTEX_URL)).rstrip("/")
        self.model = model
        self.role = role
        self.timeout = timeout
        self.temperature = temperature
        self.transport = transport or _post_chat_completion

    def resolve_model(self) -> str:
        if self.model:
            return self.model
        try:
            # Importen ligger INNE i try-blokken med vilje: den lastes fra
            # continuous_pipeline, og en ImportError derfra er akkurat den
            # resolver-feilen dette unntaket finnes for aa oversette. Laa den
            # utenfor, slapp den raa forbi den ene oversetteren.
            from agent.continuous_pipeline import default_live_model_resolver

            return default_live_model_resolver(self.role)
        except Exception as exc:  # noqa: BLE001 — enhver resolver-feil er fail-closed her
            raise ImplementationBlocked(
                f"live cortex model resolution failed: {exc}", gate="runtime"
            ) from exc

    def build_prompt(
        self,
        design: DesignRecord,
        pre_images: Mapping[str, str | None],
        *,
        budget: ScopeBudget,
    ) -> str:
        parts = [
            f"# Goal\n{design.goal_id}: {design.design.strip()}",
        ]
        if design.acceptance.strip():
            parts.append(f"# Acceptance\n{design.acceptance.strip()}")
        refs = ", ".join(r for r in (design.cad_ref, design.adr_ref, design.bl_ref) if r)
        if refs:
            parts.append(f"# References\n{refs}")
        parts.append(
            "# Allowed files (leased; anything else voids the patch)\n"
            + "\n".join(f"- {p}" for p in sorted(pre_images))
        )
        parts.append(
            "# Budget (measured from your output, not from anything you claim)\n"
            f"- at most {budget.max_files} files\n"
            f"- at most {budget.max_changed_lines} changed lines (additions + deletions)\n"
            f"- at most {budget.max_deleted_lines} deleted lines\n"
            f"- at most {budget.max_new_dependencies} new third-party imports"
        )
        parts.append(
            "# Tests that must pass afterwards\n"
            + "\n".join(f"- {t}" for t in design.tests)
        )
        for path in sorted(pre_images):
            content = pre_images[path]
            if content is None:
                parts.append(f"# Current content of {path}\n(file does not exist yet)")
            else:
                parts.append(f"# Current content of {path}\n```\n{content}\n```")
        return "\n\n".join(parts)

    def generate(
        self,
        design: DesignRecord,
        pre_images: Mapping[str, str | None],
        *,
        budget: ScopeBudget,
    ) -> ProposedPatch:
        model = self.resolve_model()
        payload = {
            "model": model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": self.build_prompt(design, pre_images, budget=budget)},
            ],
        }
        try:
            response = self.transport(f"{self.base_url}/chat/completions", payload, self.timeout)
        except ImplementationBlocked:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ImplementationBlocked(
                f"cortex call failed: {type(exc).__name__}: {exc}", gate="runtime"
            ) from exc
        text = _first_message_content(response)
        patch = parse_patch_response(text)
        return ProposedPatch(
            files=patch.files,
            rationale=patch.rationale,
            model_claimed=patch.model_claimed,
            model_id=model,
        )


def _post_chat_completion(url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise ImplementationBlocked(f"cortex HTTP {exc.code}: {detail}", gate="runtime") from exc


def _first_message_content(response: Mapping[str, Any]) -> str:
    try:
        return str(response["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise ImplementationBlocked(
            f"cortex response has no message content: {exc}", gate="runtime"
        ) from exc


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_patch_response(text: str) -> ProposedPatch:
    """Tolk generatorens svar strengt. Ingen gjetting.

    En generator som ikke klarte aa svare i formatet, har heller ikke sagt noe vi
    kan handle paa. Aa lete etter kodeblokker i fritekst ville produsert en patch av
    et svar som ikke var en patch — og den ville sett like ferdig ut som en ekte.
    """
    raw = _FENCE.sub("", str(text or "").strip())
    if not raw:
        raise ImplementationBlocked("cortex returned an empty patch response", gate="runtime")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImplementationBlocked(
            f"cortex response is not the required JSON envelope: {exc}", gate="runtime"
        ) from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("files"), list):
        raise ImplementationBlocked(
            "cortex response lacks a 'files' list", gate="runtime"
        )
    files: dict[str, str] = {}
    for item in payload["files"]:
        if not isinstance(item, Mapping):
            raise ImplementationBlocked("cortex file entry is not an object", gate="runtime")
        path = str(item.get("path") or "").strip()
        if not path:
            raise ImplementationBlocked("cortex file entry has no path", gate="runtime")
        if "content" not in item or not isinstance(item["content"], str):
            raise ImplementationBlocked(
                f"cortex file entry for {path} has no string content", gate="runtime"
            )
        if path in files:
            raise ImplementationBlocked(
                f"cortex returned {path} twice; which one is the file is undefined",
                gate="runtime",
            )
        files[path] = item["content"]
    claimed = {
        k: v
        for k, v in payload.items()
        if k in {"changed_files", "changed_lines", "deleted_lines", "new_dependencies"}
    }
    return ProposedPatch(files=files, rationale=str(payload.get("rationale") or ""), model_claimed=claimed)


# ------------------------------------------------------------- utfoereren ----


def _run_command(command: Sequence[str], cwd: Path, timeout: float) -> tuple[int, str]:
    completed = subprocess.run(  # noqa: S603 — kommandoen er injisert konfigurasjon, ikke input
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.returncode, (completed.stdout + completed.stderr)


class FaberImplementer:
    """Steg 8, som en ``build()`` :class:`~agent.code_workflow.GovernedCodeRunner` kan kalle.

    Konstruer med maalet og leasen; gi ``implementer.build`` til runneren.
    """

    def __init__(
        self,
        *,
        goal_id: str,
        repo_root: str | os.PathLike[str],
        lease_set: Sequence[str],
        design: DesignRecord | None = None,
        design_store: DesignStore | None = None,
        generator: CortexPatchGenerator | None = None,
        scope_budget: ScopeBudget | None = None,
        test_command: Sequence[str] | None = None,
        command_runner: Callable[[Sequence[str], Path, float], tuple[int, str]] | None = None,
        test_timeout: float = 1800.0,
    ):
        self.goal_id = str(goal_id)
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.lease_set = tuple(sorted({str(p).strip() for p in lease_set if str(p).strip()}))
        self._design = design
        self.design_store = design_store or DesignStore()
        self.generator = generator or CortexPatchGenerator()
        #: Samme grense som runneren haandhever. Utfoereren kjenner den for aa kunne
        #: LA VAERE aa skrive en for stor patch — ikke for aa kunne pynte paa tallet.
        self.scope_budget = scope_budget or ScopeBudget()
        self.test_command = tuple(test_command) if test_command else None
        self.command_runner = command_runner or _run_command
        self.test_timeout = test_timeout
        self._pre_images: dict[str, str | None] = {}
        self._written: tuple[str, ...] = ()
        #: Hva vi faktisk skrev, per fil. Tilbakerulling sammenligner mot DETTE, ikke
        #: mot pre-imaget, saa vi aldri ruller bort en endring som ikke er vaar.
        self._wrote: dict[str, str] = {}
        self._skipped_rollback: list[str] = []

    @classmethod
    def bound_to(cls, runner: Any, **kwargs: Any) -> "FaberImplementer":
        """Bind utfoereren til runnerens EGET budsjettobjekt.

        To eksemplarer av en grense er to grenser som kan vaere uenige. Er
        utfoererens slakkere enn runnerens, skriver den en patch runneren straks
        blokkerer — og treet staar skittent naar neste ticks steg 4 sjekker
        ``git_clean``. Denne konstruktoeren gjoer det umulig ved konstruksjon i
        stedet for aa be noen huske det.
        """
        kwargs.pop("scope_budget", None)
        return cls(scope_budget=runner.scope_budget, **kwargs)

    # -- lesing ---------------------------------------------------------------

    def design(self) -> DesignRecord:
        if self._design is None:
            self._design = self.design_store.load(self.goal_id)
        self._design.assert_actionable()
        return self._design

    def resolve(self, path: str) -> Path:
        """Loes en repo-relativ sti, og nekt alt som forlater repoet eller leasen.

        Sjekket er paa den OPPLOESTE stien: ``a/../../etc/passwd`` er inne i
        lease-settet som streng og utenfor repoet som fil. Steg 11 sammenligner
        strenger; her finnes filsystemet, saa her sjekkes filen.
        """
        candidate = (self.repo_root / path).resolve()
        if candidate != self.repo_root and self.repo_root not in candidate.parents:
            raise ImplementationBlocked(
                f"path escapes the repository: {path}", gate="landing_scope"
            )
        return candidate

    def read_pre_images(self) -> dict[str, str | None]:
        """Innholdet i lease-settet naa. ``None`` = finnes ikke enda.

        Snittet mot designets ``target_files`` er BEVISST ikke tatt: leasen er
        autoriteten paa hva som kan skrives, og et design som peker paa en ufileaset
        fil skal stoppe paa den filen, ikke forsvinne stille ut av kontekstvinduet.
        """
        images: dict[str, str | None] = {}
        for rel in self.lease_set:
            path = self.resolve(rel)
            images[rel] = path.read_text(encoding="utf-8") if path.is_file() else None
        self._pre_images = images
        return images

    # -- kontroll av forslaget ------------------------------------------------

    def vet(self, patch: ProposedPatch) -> Mapping[str, str]:
        """Avvis et forslag vi ikke har lov til, eller ikke tjener noe paa, aa skrive."""
        if not patch.files:
            raise ImplementationBlocked(
                "cortex proposed no files — step 8 produced nothing; "
                f"rationale: {patch.rationale.strip()[:300] or '(none given)'}",
                gate="implementation",
            )
        outside = sorted(set(patch.files) - set(self.lease_set))
        if outside:
            raise ImplementationBlocked(
                "patch touches files outside the lease: " + ", ".join(outside[:10]),
                gate="landing_scope",
            )
        for path, content in sorted(patch.files.items()):
            self.resolve(path)
            hits = [p.pattern for p in _CREDENTIAL_SHAPES if p.search(content)]
            if hits:
                raise ImplementationBlocked(
                    f"patch for {path} contains credential-shaped material", gate="security"
                )
            if path.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as exc:
                    raise ImplementationBlocked(
                        f"patch for {path} is not valid Python: line {exc.lineno}: {exc.msg}",
                        gate="implementation",
                    ) from exc
        unchanged = all(self._pre_images.get(p) == c for p, c in patch.files.items())
        if unchanged:
            raise ImplementationBlocked(
                "patch is byte-identical to the current files — a build that changed "
                "nothing has not built anything, and zero measured lines with green "
                "tests is exactly what the stub produced",
                gate="implementation",
            )
        return dict(patch.files)

    # -- skriving -------------------------------------------------------------

    def _current(self, rel: str) -> str | None:
        target = self.resolve(rel)
        return target.read_text(encoding="utf-8") if target.is_file() else None

    def write(self, files: Mapping[str, str]) -> tuple[str, ...]:
        """Skriv hele settet eller ingenting, og bare oppaa det vi faktisk leste.

        En delvis skrevet patch etterlater et tre ingen har designet: halvparten av
        en endring bestaar ingen test og beskrives av ingen review.

        **Pre-imaget sjekkes paa nytt rett foer hver ``os.replace``.** Mellom lesingen
        og skrivingen ligger et cortex-kall som kan ta minutter, og
        ``lease_authority`` gjoer eieren per PRINSIPAL, ikke per kjoering — to
        samtidige Faber-kjoeringer paa .15 blokkerer altsaa ikke hverandre. Uten denne
        sjekken skriver vi et helt filinnhold utledet fra en base som har flyttet
        seg, og bakser bort den andres arbeid uten aa se det. Det er `ae832c8a4`
        ett lag ned.
        """
        done: list[str] = []
        try:
            for rel in sorted(files):
                if self._current(rel) != self._pre_images.get(rel):
                    raise ImplementationBlocked(
                        f"{rel} changed on disk after step 8 read it — the patch was "
                        "derived from a base that has moved; writing it would discard "
                        "the other change unseen",
                        gate="lease",
                    )
                target = self.resolve(rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(files[rel])
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp, target)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                self._wrote[rel] = files[rel]
                done.append(rel)
        except Exception:
            self._restore(done)
            raise
        self._written = tuple(done)
        return self._written

    def rollback(self) -> tuple[str, ...]:
        """Sett lease-settet tilbake til pre-imagene. Idempotent."""
        restored = self._restore(self._written)
        self._written = ()
        return restored

    def _restore(self, paths: Sequence[str]) -> tuple[str, ...]:
        """Angre VAAR EGEN skriving, aldri noen andres.

        En tilbakerulling som skriver pre-imaget tilbake ubetinget er en ny
        overskriving: rakk noen andre aa endre filen etter at vi skrev den, ville
        opprydningen vaert nettopp den skaden den skulle rydde opp etter. Vi ruller
        derfor bare tilbake filer som fortsatt inneholder det VI skrev.
        """
        restored: list[str] = []
        for rel in paths:
            if self._current(rel) != self._wrote.get(rel):
                self._skipped_rollback.append(rel)
                continue
            before = self._pre_images.get(rel)
            target = self.resolve(rel)
            if before is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(before, encoding="utf-8")
            self._wrote.pop(rel, None)
            restored.append(rel)
        return tuple(restored)

    # -- testing --------------------------------------------------------------

    def test_targets(self, design: DesignRecord) -> tuple[str, ...]:
        """Valider det designet navngir som test, foer det blir argv.

        ``pytest -q --collect-only`` avslutter med 0 uten aa kjoere en eneste test.
        Gikk designets ``tests`` uvalidert inn i argv, ville et flagg der gitt exit 0,
        og ``build()`` ville satt groenn testevidens for en kjoering som ikke testet
        noe. Groenn uten aa ha kjoert er verre enn roed.
        """
        for target in design.tests:
            if target.startswith("-"):
                raise ImplementationBlocked(
                    f"design test target is a flag, not a test: {target} — a flag can "
                    "make pytest exit 0 without running anything",
                    gate="design_gate",
                )
            head = target.split("::", 1)[0]
            if not (self.repo_root / head).exists():
                raise ImplementationBlocked(
                    f"design names a test path that does not exist: {target}",
                    gate="design_gate",
                )
        return design.tests

    def run_tests(self, design: DesignRecord) -> tuple[bool, str]:
        command = self.test_command or (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *self.test_targets(design),
        )
        try:
            code, output = self.command_runner(command, self.repo_root, self.test_timeout)
        except subprocess.TimeoutExpired:
            return False, f"tests timed out after {self.test_timeout}s"
        except Exception as exc:  # noqa: BLE001
            return False, f"test command failed to run: {type(exc).__name__}: {exc}"
        tail = "\n".join(line for line in output.strip().splitlines() if line.strip())[-600:]
        return code == 0, tail or f"exit {code} with no output"

    # -- selve steget ---------------------------------------------------------

    def build(self) -> dict[str, Any]:
        """Kjoer steg 8 én gang og returner evidensen runneren doemmer.

        Returnerer ``tests`` KUN naar testene faktisk var groenne. Runneren godtar en
        hvilken som helst ikke-tom verdi, saa en ``"FAILED: 3"`` herfra ville passert
        som testevidens.
        """
        self._skipped_rollback = []
        design = self.design()
        # FOER enhver sideeffekt. Laa denne sjekken i `run_tests()`, kjoerte den
        # etter `write()` — og en blokkering paa design-gaten etterlot da et skrevet
        # tre uten tilbakerulling. Samme feilklasse som en sen sikkerhetsjekk: en
        # gate som fyrer etter skrivingen rydder ikke opp etter den.
        self.test_targets(design)
        pre = self.read_pre_images()
        patch = self.generator.generate(design, pre, budget=self.scope_budget)
        files = self.vet(patch)

        radius = measure_blast_radius(pre, files, repo_root=self.repo_root)
        evidence: dict[str, Any] = {
            **radius.as_evidence(),
            "diff_id": diff_id_for(files),
            "model": patch.model_id,
            "design_ref": str(self.design_store.path_for(self.goal_id)),
            "blast_radius_source": "measured:pre-image-diff",
            "written_files": "",
        }
        mismatch = _claim_mismatch(patch.model_claimed, radius)
        if mismatch:
            # Ikke en overstyring — et funn. En generator som paastaar noe annet enn
            # bytesene sine, har sagt noe falsifiserbart, og det ble falsifisert.
            evidence["model_claimed_mismatch"] = mismatch
        if radius.dependencies:
            evidence["new_dependency_names"] = ", ".join(radius.dependencies)

        within, violations = self.scope_budget.evaluate(
            changed_files=radius.changed_files,
            changed_lines=radius.changed_lines,
            deleted_lines=radius.deleted_lines,
            new_dependencies=radius.new_dependencies,
        )
        if not within:
            # De ekte tallene gaar ut uendret. Aa skrive dem ned til under grensen
            # her ville vaert nettopp feilklassen kjeden er bygget for aa hindre —
            # og den ville vaert usynlig, fordi alt annet saa riktig ut.
            #
            # KASTES, ikke returneres: en retur uten ``tests`` blokkeres av runneren
            # paa gaten ``tests`` med teksten «build returned no test evidence», og
            # da er den ekte aarsaken borte fra baade blocker og journal.
            #
            # PRESIST hva som overlever: runnerens ytre haandterer beholder bare
            # ``str(exc)``. ``evidence`` og ``gate`` her forkastes av den, saa
            # aarsaksTEKSTEN naar journalen — tallene og gate-navnet gjoer det ikke.
            # Aa la dem overleve er en endring i runneren, ikke her.
            evidence["scope_refusal"] = "; ".join(violations)
            evidence["rationale"] = _redact(patch.rationale[:2000])
            raise ImplementationBlocked(
                "build exceeds scope budget: " + "; ".join(violations)
                + f" — measured {radius.changed_files} file(s), {radius.changed_lines} "
                  "changed line(s); nothing was written",
                gate="scope_budget",
                evidence=self._safe_evidence(evidence),
            )

        written = self.write(files)
        evidence["written_files"] = ",".join(written)
        passed, output = self.run_tests(design)
        evidence["rationale"] = _redact(patch.rationale[:2000])
        if not passed:
            # Samme behandling som scope-avvisningen, og av samme grunn: en retur
            # uten ``tests`` blokkeres av runneren paa «build returned no test
            # evidence», og da har journalen lagret feil aarsak. Neste tick proever
            # igjen uten aa vite HVILKEN test som feilet.
            rolled = self.rollback()
            evidence["test_failure"] = _redact(output)
            evidence["written_files"] = ""
            evidence["rolled_back"] = ",".join(rolled)
            if self._skipped_rollback:
                evidence["rollback_skipped"] = ",".join(sorted(set(self._skipped_rollback)))
            raise ImplementationBlocked(
                "targeted tests failed after the patch was written; tree rolled back: "
                + _redact(output)[:400],
                gate="tests",
                evidence=self._safe_evidence(evidence),
            )
        evidence["tests"] = _redact(output)
        return self._safe_evidence(evidence)

    def _safe_evidence(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        """Bakstopper: ingen evidens forlater steg 8 med kreditiv-formet materiale.

        Fritekstfeltene er allerede redigert av :func:`_redact`; dette fanger det
        redigeringen ikke saa. Utloeser den, er en skriving allerede skjedd, saa
        treet rulles tilbake foer vi kaster — ellers staar treet skittent og neste
        ticks steg 4 (``git_clean``) feiler paa vaart eget rot.
        """
        payload = dict(evidence)
        try:
            SecretPolicy.assert_safe_payload(payload)
        except PermissionError as exc:
            self.rollback()
            raise ImplementationBlocked(
                f"step 8 evidence carries credential-like material: {exc}",
                gate="security",
            ) from exc
        return payload


def diff_id_for(files: Mapping[str, str]) -> str:
    """Identiteten til et konkret filsett, bundet til bytesene.

    Steg 10 sammenligner reviewerens ``diff_id`` mot buildens. Er id-en et loepenummer
    eller et tidsstempel, kan de matche selv om reviewer saa noe annet enn det som
    ble skrevet — og da beviser sammenligningen ingenting.
    """
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path].encode("utf-8"))
        digest.update(b"\0")
    return "faber8-" + digest.hexdigest()[:16]


def _claim_mismatch(claimed: Mapping[str, Any], radius: BlastRadius) -> str:
    measured = radius.as_evidence()
    parts = []
    for key, value in sorted(claimed.items()):
        try:
            asserted = int(value)
        except (TypeError, ValueError):
            parts.append(f"{key}: claimed {value!r} (not a number), measured {measured.get(key)}")
            continue
        if asserted != measured.get(key):
            parts.append(f"{key}: claimed {asserted}, measured {measured.get(key)}")
    return "; ".join(parts)
