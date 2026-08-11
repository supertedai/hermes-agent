"""Runtime binding for the governed Faber Code workflow.

This adapter is intentionally small: evidence collection stays outside the
workflow kernel, while this boundary makes PreflightResult mandatory before a
Faber build can run and persists a blocked handoff for the next tick.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from agent.code_workflow import (
    FaberGoal,
    FaberHandoff,
    FaberGoalRegistry,
    GoalState,
    GovernedCodeRunner,
    HandoffStore,
    LandingEvidence,
    PreflightGate,
    PreflightInput,
    PreflightResult,
    PostcommitResult,
    ReviewEvidence,
    ReviewVerdict,
    GovernedRunResult,
)


@dataclass(frozen=True)
class FaberRuntimeResult:
    """Result of one runtime tick at the governed Code boundary."""

    run: GovernedRunResult
    preflight: PreflightResult
    postcommit: PostcommitResult | None = None
    learning_event: Mapping[str, object] | None = None


class FaberRuntime:
    """Bind source evidence, the hard preflight gate, and the runner.

    The adapter never invents evidence and never commits or starts services.
    A failed preflight is converted into a blocked goal and, when configured,
    an atomic handoff file for the next tick.
    """

    def __init__(
        self,
        *,
        preflight: PreflightGate | None = None,
        runner: GovernedCodeRunner | None = None,
        handoff_store: HandoffStore | None = None,
        goal_registry: FaberGoalRegistry | None = None,
    ) -> None:
        self.preflight_gate = preflight or PreflightGate()
        self.runner = runner or GovernedCodeRunner()
        self.handoff_store = handoff_store
        self.goal_registry = goal_registry

    def tick(
        self,
        goal: FaberGoal,
        evidence: PreflightInput,
        *,
        build: Callable[[], Mapping[str, str]],
        review: Callable[[Mapping[str, str]], ReviewEvidence],
        landing: Callable[[Mapping[str, str]], LandingEvidence],
        prelanding_evidence: LandingEvidence | None = None,
        postcommit: Callable[[GovernedRunResult], PostcommitResult] | None = None,
        learning: Callable[[GovernedRunResult, PostcommitResult], Mapping[str, object]] | None = None,
    ) -> FaberRuntimeResult:
        """Run exactly one governed tick; build is unreachable without PASS."""
        if self.goal_registry is not None:
            self.goal_registry.put(goal)
        preflight = self.preflight_gate.evaluate(evidence)
        result = self.runner.run(
            goal,
            preflight=preflight,
            build=build,
            review=review,
            landing=landing,
            prelanding_evidence=prelanding_evidence,
        )
        postcommit_result = (
            postcommit(result)
            if postcommit is not None and result.goal.state is GoalState.LANDED
            else None
        )
        learning_event = (
            dict(learning(result, postcommit_result))
            if learning is not None and postcommit_result is not None and postcommit_result.success
            else None
        )
        if result.handoff is not None and self.handoff_store is not None:
            self.handoff_store.save(result.handoff)
        if self.goal_registry is not None:
            self.goal_registry.put(result.goal)
        return FaberRuntimeResult(run=result, preflight=preflight, postcommit=postcommit_result, learning_event=learning_event)


def handoff_path(path: str | Path) -> HandoffStore:
    """Create the profile/repo-local durable handoff adapter."""
    return HandoffStore(path)


def build_callable(payload: Mapping[str, object], runner: GovernedCodeRunner,
                   evidence: PreflightInput) -> Callable[[], Mapping[str, object]]:
    """Velg hva steg 8 faktisk ER for denne ticken.

    BL-4050. Til nå fantes bare den ene grenen::

        build=lambda: payload["build"]

    Kjeden leste altså sin egen blast-radius ut av det samme JSON-objektet som ba
    den om å kjøre. Vakten fra BL-4029 var ekte, men den dømte et tall avsenderen
    hadde skrevet selv — en måling som er et sitat.

    Med ``payload["implement"]`` bygges i stedet en :class:`FaberImplementer`, som
    kaller cortex, skriver filer og MÅLER endringen fra bytes på disk.

    To ting bindes her, og begge er poenget:

    * **Budsjettet** hentes fra runneren (``bound_to``), ikke fra payloaden. Ellers
      finnes to grenser som kan være uenige.
    * **Lease-settet** hentes fra ``source_refs["lease"]`` — nøyaktig den referansen
      steg 4 sjekket og steg 11 sammenligner landingssettet mot. Å la payloaden
      oppgi et eget lease-sett ville gitt skriveren lov til å definere sin egen
      grense, og da beviser hverken steg 4 eller steg 11 noe.

    Den literale grenen beholdes for replay og testrigger, men den er nå navngitt
    som det den er, ikke som en utfører.
    """
    # BL-4070 (reviewer 2): naervaer, ikke sannhetsverdi — ogsaa her.
    # `{"implement": {}}` gikk stille tilbake til den literale grenen og
    # gjenopprettet dermed selv-attesteringen BL-4050 fjernet.
    if "implement" in payload:
        spec = payload.get("implement")
        if not isinstance(spec, Mapping) or not spec:
            raise ValueError(
                "'implement' is present but empty — an empty spec silently reverted step 8 "
                "to the literal branch, which is the self-attested measurement BL-4050 removed")
    else:
        spec = None
    if not spec:
        literal = payload.get("build")
        if literal is None:
            raise ValueError("tick payload needs either 'implement' or a literal 'build'")
        return lambda: dict(literal)  # type: ignore[arg-type]
    if not isinstance(spec, Mapping):
        raise ValueError("'implement' must be an object")
    from agent.faber_implementer import DesignStore, FaberImplementer

    lease = tuple(
        part.strip()
        for part in str(evidence.source_refs.get("lease", "")).split(",")
        if part.strip()
    )
    if not lease:
        raise ValueError(
            "source_refs['lease'] names no files — the writer cannot be confined to "
            "a lease that does not say what it covers")
    goal_spec = payload.get("goal") or {}
    implementer = FaberImplementer.bound_to(
        runner,
        goal_id=str(spec.get("goal_id") or (goal_spec.get("goal_id") if isinstance(goal_spec, Mapping) else "")),
        repo_root=str(spec["repo_root"]),
        lease_set=lease,
        design_store=DesignStore(spec["design_root"]) if spec.get("design_root") else None,
        test_command=tuple(spec["test_command"]) if spec.get("test_command") else None,
    )
    return implementer.build



def lease_take(payload: Mapping[str, object], evidence: PreflightInput) -> PreflightInput:
    """STEG 6. Ta leasen hos autoriteten, og la SVARET bli kjedens lease-sett.

    BL-4070. Til nå tok kjeden den ingen steder. `lease_authority` kjørte hvert
    tjuende minutt via `faber_observe`, men det er en OBSERVASJON — ingen av de
    tretten stegene ba noen gang om å få eie noe.

    To halvdeler, og bare den ene er åpenbar:

    * **Ta leasen.** `claim()` er fail-closed: ingen token, uåbar autoritet eller
      5xx gir ``ok=False``, ikke «antatt tatt».
    * **Bytt kilde.** ``source_refs["lease"]`` settes til autoritetens
      ``acquired``-liste. Uten dette ville steg 11 fortsatt sammenlignet det
      MÅLTE landingssettet mot en streng PRODUSENTEN skrev — og da beviser
      hverken steg 4 eller steg 11 noe. Å ta leasen uten å bytte kilde lukker
      halve hullet og ser helt lukket ut.

    **Hvorfor dette ligger i `_cli()` og ikke i :meth:`FaberRuntime.tick`.**
    `build_callable` binder utføreren til ``source_refs["lease"]``. Skjedde
    claimet inne i `tick`, ville `build` allerede vært bundet til payloadens
    lease-sett mens gaten dømte autoritetens — to kilder for én grense. Det er
    nøyaktig defekten BL-4050 lukket ett steg over. Claimet skjer derfor FØR
    både `build_callable` og `tick`, og det finnes bare én sti.

    Feiler claimet, returneres evidens med ``lease_clear=False`` og et TOMT
    lease-sett. Begge blokkerer: steg 4 på flagget, `build_callable` på at settet
    ikke sier hva det dekker. En mislykket lease kan altså ikke bli til en tick
    som bygger noe.

    **NÆRVÆR, IKKE SANNHETSVERDI.** Alle tre spec-nøklene i denne modulen
    (``lease``, ``land``, ``postcommit``) avgjøres av om nøkkelen FINNES, ikke
    av om verdien er tom. ``{"postcommit": {}}`` betyr «kjør steg 12/13 med
    standardvalg» — med en truthiness-test ble det STILLE til «hopp over
    tilbakelesingen». Det er nøyaktig den stille utelatelsen resten av kjeden
    er bygget for å hindre, og min egen test fant den. Er nøkkelen til stede
    men verdien ubrukelig, kastes det — den blir aldri til en tick som går
    videre uten steget.
    """
    if "lease" not in payload:
        return evidence
    spec = payload.get("lease")
    if not isinstance(spec, Mapping):
        raise ValueError("'lease' must be an object")
    from agent.lease_authority import DEFAULT_TTL, claim, scope_paths

    declared = spec.get("paths")
    if isinstance(declared, str):
        paths = scope_paths(declared)
    elif isinstance(declared, (list, tuple)):
        paths = tuple(str(x).strip() for x in declared if str(x).strip())
    else:
        raise ValueError("'lease.paths' must be a string scope or a list of paths")
    # ALT SOM KAN KASTE MAA SKJE FOER `claim()`. Reviewer runde 3: `dict(...)` sto
    # ETTER claimet, og `PreflektInput.source_refs` er et udekorert dataclass-felt
    # uten validering — `"source_refs": null` eller en skalar konstruerer fint og
    # sprekker foerst her, med leasen allerede tatt. Da lekker den forbi
    # `_cli`s `finally`, fordi `lease_take` kalles FOER den `try`-en.
    #
    #     source_refs=null   rc=2 claimed=1 released=0
    #     source_refs="abc"  rc=2 claimed=1 released=0
    #
    # Etter dette er funksjonen TOTAL etter `claim()`: `ttl` parses over,
    # `outcome.acquired` bygges av `_clean(paths)` inne i `claim`, og `",".join`
    # over strenger kan ikke kaste. Aa flytte kallet inn i `try`-en i stedet ville
    # vaert et annet galt svar: `evidence` i `finally` er da PRE-claim, saa
    # `lease_release` ville sluppet payloadens deklarerte streng i stedet for
    # autoritetens `acquired`.
    refs = dict(evidence.source_refs)
    outcome = claim(paths, ttl=int(spec.get("ttl") or DEFAULT_TTL),
                    note=str(spec.get("note") or ""))
    refs["lease"] = ",".join(outcome.acquired) if outcome.ok else ""
    refs["lease_authority"] = outcome.reason
    return replace(evidence, lease_clear=bool(outcome.ok), source_refs=refs)


def lease_release(payload: Mapping[str, object], evidence: PreflightInput) -> str:
    """Slipp det ticken tok. (BL-4070, reviewer non-blocking 1)

    Uten dette sto hver ``--tick-json`` med en `lease`-blokk igjen med en lease
    paa inntil TTL (default 3600 s) paa stier flere oekter deler — trap 3 i
    `lease_authority`s egen modul-docstring, gjenskapt av innkoblingen som
    skulle bruke den. Slippes det som FAKTISK ble tatt (autoritetens svar), ikke
    det som ble bedt om.

    Returnerer en note; feiler aldri. En mislykket release skal ikke velte en
    tick som allerede er ferdig — men den skal SES, og noten baeres derfor ut i
    CLI-ens rapport.
    """
    if "lease" not in payload:
        return ""
    held = tuple(part for part in str(evidence.source_refs.get("lease", "")).split(",") if part)
    if not held:
        return "ingen lease aa slippe (claimet feilet)"
    try:
        from agent.lease_authority import release

        ok, note = release(held)
        return note if ok else f"lease IKKE sluppet: {note}"
    except Exception as exc:  # pragma: no cover - transportfeil
        return f"lease-release kastet: {type(exc).__name__}: {exc}"


class LandingObservation:
    """Det steg 11 FAKTISK landet, båret fram til steg 12/13.

    Runneren kaster landingsevidensen etter overgangen til LANDED: bare
    ``goal.evidence["commit"]`` overlever, ikke filsettet. Steg 13 trenger
    nettopp filsettet — og å hente det fra payloadens ``prelanding`` ville gjort
    tilbakelesingen til en sammenligning mot noe AVSENDEREN skrev. Det er den
    selv-attesterte målingen BL-4050 fjernet fra steg 8, gjenoppstått to steg
    senere.

    Denne holderen bærer derfor evidensen `GitLandingExecutor` leste TILBAKE fra
    git. Ble den aldri fylt (den literale grenen), nekter steg 12/13 heller enn
    å falle tilbake på det deklarerte settet.
    """

    __slots__ = ("evidence",)

    def __init__(self) -> None:
        self.evidence: LandingEvidence | None = None


def landing_callable(payload: Mapping[str, object], prelanding: LandingEvidence | None,
                     literal: LandingEvidence, *,
                     observed: LandingObservation | None = None,
                     ) -> Callable[[Mapping[str, str]], LandingEvidence]:
    """Velg hva steg 11 faktisk ER for denne ticken.

    BL-4070. Til nå fantes bare den ene grenen::

        landing=lambda _: landing

    Runtimen forsynte altså sin egen landing. `faber_landing` — hånden som
    faktisk stager, commiter og leser tilbake — hadde NULL importører, og
    `faber_postcommit_adapters` hadde én: `faber_landing`, som selv var
    uoppnåelig. Vakten i `tests/test_chain_is_wired.py` er skrevet for nettopp
    denne formen: bygget, ikke koblet.

    Med ``payload["land"]`` bygges i stedet
    :func:`agent.faber_landing.landing_callable`, som lander MOT git og
    returnerer den MÅLTE commiten og det MÅLTE filsettet.

    Settet kan ikke oppgis her. Det utledes av ``prelanding.landing_set`` — samme
    verdi `LandingScopeGate` måler mot leasen inne i runneren. Med to innganger
    landet en uleaset fil, og målet gikk til LANDED (BL-4051). Derfor er
    ``prelanding`` PÅKREVD på den ekte grenen: uten den finnes ikke settet vakten
    dømte, og en landing uten dømt sett er ikke en gatet landing.

    Den literale grenen beholdes for replay og testrigger, navngitt som det den
    er. Den fyller ikke ``observed``: en literal er ikke en måling.
    """
    if "land" not in payload:
        return lambda _: literal
    spec = payload.get("land")
    if not isinstance(spec, Mapping):
        raise ValueError("'land' must be an object")
    if prelanding is None:
        raise ValueError(
            "'land' requires 'prelanding': the landing set comes from the evidence "
            "the scope gate judged, never from the payload that asked for the landing")
    message = str(spec.get("message") or "").strip()
    if not message:
        raise ValueError("'land.message' is required — a commit nobody can read is not a landing")
    from agent.faber_landing import landing_callable as _git_landing

    hand = _git_landing(message=message, prelanding=prelanding, repo=spec.get("repo"))
    if observed is None:
        return hand

    def _land_and_observe(build_evidence: Mapping[str, str]) -> LandingEvidence:
        result = hand(build_evidence)
        observed.evidence = result
        return result

    return _land_and_observe


def postcommit_callable(payload: Mapping[str, object], observed: LandingObservation,
                        ) -> Callable[[GovernedRunResult], PostcommitResult] | None:
    """Velg hva steg 12/13 faktisk ER for denne ticken.

    BL-4070. `PostcommitLoop` fantes, og de sju adapterne den trenger fantes i
    `faber_postcommit_adapters`. Ingen bandt dem sammen: CLI-en kalte `tick()`
    uten ``postcommit``, så røyktesten og tilbakelesingen kjørte aldri.

    Fire av de sju stegene kan ALDRI replayes fra journalen (``tests``,
    ``runtime_smoke``, ``readback``, ``rollback``) — de BEVISER noe, de
    registrerer det ikke. Den regelen bor i `PostcommitLoop`, ikke her; denne
    funksjonen binder bare de ekte adapterne til den, slik at «DONE» betyr at
    noe kjørte.

    **PÅ `.15` KJØRER BARE DEN ENE GRENEN, OG DET BØR STÅ HER.** `docker` er ikke
    installert, og `local_fleet_state()` leser et manglende binærfil som et
    POSITIVT funn av tomhet, så `RetiredFleetGate` passerer. Grenen som faktisk
    måler en kjørende prosess mot commitens digest — `container` — er dermed
    uoppnåelig her. Det som gjenstår er `no_runtime_target`, som registrerer en
    ERKLÆRING. «Steg 12 kjørte på `.15`» betyr altså «steg 12 registrerte en
    erklæring», ikke «steg 12 målte en prosess». Regelen om nøyaktig ett svar
    tvinger erklæringen fram i klartekst i stedet for å la stillhet bli lest som
    en måling — men den gjør ikke erklæringen sann.

    ``expected_files`` kommer fra :class:`LandingObservation` — det git leste
    tilbake — aldri fra payloaden. Er holderen tom, har ingen hånd landet noe,
    og steg 12/13 nekter i stedet for å lese tilbake mot et selvoppgitt sett.

    ``reviewer`` settes til PASS fordi tilstanden ALLEREDE beviser det: `tick`
    kaller denne kun når målet står i LANDED, og `FaberGoalLedger.transition`
    hever `PermissionError` med mindre ReviewEvidence bærer PASS. Verdien er
    utledet av tilstanden, ikke antatt om den.
    """
    if "postcommit" not in payload:
        return None
    spec = payload.get("postcommit")
    if not isinstance(spec, Mapping):
        raise ValueError("'postcommit' must be an object")
    from agent.code_workflow import PostcommitLoop
    from agent import faber_postcommit_adapters as pca

    repo = Path(str(spec["repo"])).expanduser() if spec.get("repo") else None
    test_paths = tuple(str(x) for x in (spec.get("test_paths") or ()))
    require_ref = str(spec.get("require_ref") or "")

    # BLOCK 4. `run_tests` returnerer "" med mindre pytest-oppsummeringen sier
    # «passed», og pytest over en KILDEFIL samler ingenting. Å defaulte til
    # landingssettet gjorde derfor `{"postcommit": {}}` umulig å bestå — akkurat
    # den formen presence-not-truthiness-fiksen gjorde nåbar. Testmålet er en
    # opplysning ingen kan utlede fra filsettet, så det KREVES.
    if not test_paths:
        raise ValueError(
            "'postcommit.test_paths' is required: pytest over the landed source files "
            "collects nothing, so defaulting to the landing set makes step 12/13 "
            "unpassable by construction")

    # BLOCK 1. `runtime_smoke_step` har ingen `modules`-parameter — den gamle
    # `smoke_modules` traff ingenting og ville kastet TypeError på hver ekte
    # tick. Verre: min egen test var grønn fordi FAKEN hadde en signatur den
    # ekte funksjonen ikke kan ha. Det som faktisk kreves er BL-4052 reviewer
    # B1s regel: nøyaktig ETT av kjøretidsmål eller erklært fravær, ingen av
    # dem med en default som slipper igjennom. Den regelen håndheves her, ved
    # spec-lesing, i stedet for å bli slukt av `PostcommitLoop`s ytre except.
    container = str(spec.get("container") or "").strip()
    no_runtime_target = str(spec.get("no_runtime_target") or "").strip()
    if bool(container) == bool(no_runtime_target):
        raise ValueError(
            "'postcommit' needs exactly one of 'container' or 'no_runtime_target': a "
            "landing with no measured process must SAY so, and silence about it is read "
            "downstream as if it had been measured")
    smoke_kwargs = {
        "container": container,
        "no_runtime_target": no_runtime_target,
        "host_path": str(spec.get("host_path") or ""),
        "repo_relpath": str(spec.get("repo_relpath") or ""),
    }
    if "check_local_fleet" in spec:
        smoke_kwargs["check_local_fleet"] = bool(spec["check_local_fleet"])
    loop = PostcommitLoop(readback_path=spec.get("readback_path") or None)

    def _run(result: GovernedRunResult) -> PostcommitResult:
        # Reviewer 4: entailmenten LANDED => PASS er ekte, men den bodde i en
        # annen funksjon. Her er den selvbaerende.
        if result.goal.state is not GoalState.LANDED:
            return PostcommitResult(
                False, None, ("state",),
                f"steg 12/13 ble kalt paa et maal i {result.goal.state.value}, ikke LANDED — "
                "reviewer-PASS er utledet av LANDED og gjelder ikke her")
        landed = observed.evidence
        if landed is None:
            return PostcommitResult(
                False, None, ("landing",),
                "steg 12/13 har ingen MAALT landingsresultat: ingen hand landet noe denne "
                "ticken. Aa lese commiten tilbake mot payloadens eget filsett ville "
                "sammenlignet avsenderen med seg selv")
        commit = str(landed.commit or "").strip()
        expected = tuple(landed.landing_set or ())
        if not commit or not expected:
            return PostcommitResult(
                False, None, ("commit",),
                "maalt landing mangler sha eller filsett — en landing uten begge kan "
                "ikke leses tilbake")
        return loop.run(
            commit=commit,
            reviewer=ReviewVerdict.PASS,
            tests=lambda: pca.run_tests(test_paths, repo=repo),
            commit_closer=lambda c: pca.commit_closer(c, repo=repo),
            brain_change_log=lambda c: pca.brain_change_log(c, repo=repo),
            selfstate=lambda c: pca.selfstate(c, repo=repo),
            readback=lambda c: pca.postcommit_readback(
                c, expected_files=expected, require_ref=require_ref, repo=repo),
            runtime_smoke=lambda c: pca.runtime_smoke_step(c, repo=repo, **smoke_kwargs),
            rollback=lambda c: pca.rollback(c, repo=repo),
        )

    return _run



#: Grunner som IKKE diskvalifiserer et maal fra en drevet tick, fordi steg 6 er
#: nettopp det som fjerner dem. Alt annet er en ekte blokkering og maalet
#: hoppes over med grunnen intakt.
_LEASE_ONLY_REASONS = (
    "missing authoritative source refs: lease",
    "target lease is not clear",
)


def _drivable(reasons) -> bool:
    """Er de gjenvaerende grunnene BARE de steg 6 fjerner?

    Observatoeren claimer aldri (den er en lesning), saa et maal som staar igjen
    med kun lease-grunner har klarert alt steg 4 kan svare paa uten aa handle.
    Et maal med EN ANNEN grunn i tillegg hoppes over -- vi fjerner ikke en
    blokkering ved aa la vaere aa se paa den.
    """
    if reasons is None:
        # REVIEWER BLOCK 2. `all()` over tomt er vakuoest sant, saa en pakke UTEN
        # `reasons`-noekkel i det hele tatt leste som «helt klar» — og da ble
        # `git_clean: True` og `scope_executable: True` haevdet fra ingenting.
        # Fravaer av en grunnliste er ikke fravaer av grunner.
        return False
    return all(r in _LEASE_ONLY_REASONS for r in reasons)


def isolated_build_root(repo: str, into: str, ref: str = "HEAD") -> str:
    """`git archive <ref>` inn i `into`. Ren LESING av det delte treet.

    `ref` er DEN VERIFISERTE shaen, ikke `HEAD` (reviewer N1). Driveren
    sammenligner `git_head(repo)` mot pakkens `git_ref` og arkiverer deretter —
    men mellom de to kan en parallell stroem commite, og da bygger vi C mens
    provenansen sier A. Det er BLOCK 2 om igjen med et millisekund-vindu i stedet
    for tjue minutter. Aa arkivere den verifiserte shaen laaser ARKIVETS INNHOLD:
    `git archive <sha>` leser commit-treet, saa en senere commit kan ikke endre
    det vi bygger. Kalleren laaser den ANDRE halvdelen -- at renheten ble maalt
    mot samme tilstand -- ved aa lese HEAD paa nytt etter `scope_is_clean`.

    PRESIST: den laasingen gjelder COMMITS. To residualer staar igjen, begge
    akseptable i dag: (a) ABA -- commit og reset tilbake til samme sha inne i
    vinduet; arkivet er fortsatt riktig, men renheten ble maalt mot B. (b) En
    parallell stroem som SKITNER en scope-fil uten aa commite: ingen av de to
    lesningene beveger seg, saa ingenting fanger det. Skaden er i dag begrenset
    til provenans-linja -- arkivet er pinnet, ingen reviewer doemmer, ingenting
    lander.

    HVORFOR STEG 8 IKKE FAAR SKRIVE I ARBEIDSTREET. `FaberImplementer.build`
    kaller cortex og SKRIVER FILER. Peker vi den paa `/home/agent/agent-layer/
    hermes-agent`, skriver en autonom sloeyfe inn i et tre aatte parallelle
    stroemmer deler -- og en kraesj midt i en skriving etterlater halv kode som
    neste `git add -A` fra en annen oekt kan lande. Det er noeyaktig faren
    `tools/mutation_probe.py` ble skrevet om for aa unngaa, og den gjelder
    dobbelt naar skriveren er en modell paa en timer.

    Kopien er dessuten HEAD, ikke arbeidstreet: bygget skal ikke stables paa
    andres ukommitterte arbeid. Det var BL-3643-defekten (levende kode utenfor
    git) sett fra den andre siden.
    """
    from pathlib import Path

    dest = Path(into)
    dest.mkdir(parents=True, exist_ok=True)
    # N4: STROEMMET, ikke bufret. `capture_output=True` holdt hele arkivet i
    # minnet (maalt 160 MB) og `input=` holdt en kopi til -- ~320 MB topp per
    # maal paa en vert med 9,3 GB ledig. Uholdbart naar dette skal paa en timer.
    # N3: stderr dreneres FOERST etter at tar er ferdig. `git archive` skriver
    # normalt ingenting dit; skulle den skrive >64 KB, blokkerer den til tars
    # timeout paa 600 s framfor aa henge for alltid. Bevisst, og bundet.
    with subprocess.Popen(["git", "-C", repo, "archive", ref],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as src:
        tar = subprocess.run(["tar", "-x", "-C", str(dest)], stdin=src.stdout,
                             capture_output=True, timeout=600)
        if src.stdout:
            src.stdout.close()
        src_err = (src.stderr.read().decode(errors="replace")[:200] if src.stderr else "")
        rc = src.wait()
    if rc != 0:
        raise RuntimeError(f"git archive feilet: {src_err}")
    if tar.returncode != 0:
        raise RuntimeError(f"tar feilet: {tar.stderr.decode(errors='replace')[:200]}")
    return str(dest)


def skills_for_goal(observation: Mapping[str, object], goal: Mapping[str, object]) -> dict:
    """TVERS: hvilke skills gjelder dette maalet? (BL-4087)

    `skill_selector` var koblet til broen og til gateway-flaten, men den DREVNE
    kjeden spurte den aldri -- saa steg 8 bygget uten aa vite hvilke skills som
    gjaldt oppgaven. Seleksjonen feiler aldri: mangler indeksen blir dekningen
    UNKNOWN, og UNKNOWN forplanter seg framfor aa bli en paastand om fravaer.
    """
    from agent.skill_selector import select_for_task

    text = " ".join(str(x or "") for x in (
        goal.get("title"), goal.get("bl_ref"),
        (goal.get("evidence") or {}).get("repo_scope"),
        observation.get("next_step"))).strip()
    if not text:
        return {"queryable": False, "coverage": "UNKNOWN", "selected": []}
    return select_for_task(text, stage="chain:drive").to_json()



def _resolve_ref(ref: str) -> str:
    """Slaa opp en kontrakt-referanse i registeret. Tom streng naar ingen ref.

    ÉN implementasjon, importert -- ikke gjenfortalt. To kopier av denne regelen
    ville divergert paa foerste endring, som er nettopp det som skjedde da
    `payload_for` og `evidence_for` fikk hver sin.
    """
    if not ref.strip():
        return ""
    from agent.faber_observe import resolve_contract_ref

    return resolve_contract_ref(ref)[0]


def payload_for(observation: Mapping[str, object], goal: Mapping[str, object], *,
                repo: str, build_root: str, test_command: Sequence[str]) -> dict:
    """Bygg tick-payloaden for ett maal, fra det som ER MAALT.

    Ingenting oppgraderes paa veien inn. `git`-refen kommer fra observasjonens
    `git_ref` (maalt av `faber_observe.git_head`), lease-settet fra maalets eget
    `repo_scope`, og statusene fra maalets egne felter -- ikke fra defaults som
    ville aapnet en gate paa et grunnlag ingen har etablert.

    SKYGGE VED KONSTRUKSJON: `land` og `postcommit` settes ALDRI her. Uten
    `land` tar steg 11 den literale grenen, og uten `postcommit` returnerer steg
    12/13 `None`. Aa gi denne stien landingsevne er ADR-062 V5 og hard-limit #3
    -- Mortens beslutning, ikke en flagg-verdi i denne funksjonen.
    """
    ev = dict(goal.get("evidence") or {})
    scope = str(ev.get("repo_scope", ""))
    return {
        "goal": {
            "goal_id": str(goal.get("goal_id", "")),
            "title": str(goal.get("title", "")),
            "cad_ref": str(goal.get("cad_ref", "")),
            "adr_ref": str(goal.get("adr_ref", "")),
            "bl_ref": str(goal.get("bl_ref", "")),
            "rollback": str(goal.get("rollback", "")),
        },
        "evidence": {
            "git_clean": True,
            "lease_clear": False,
            # BL-4095 (reviewer BLOCK 1). DETTE er stien kjeden faktisk gater
            # paa: dicten blir `PreflightInput` og dommes av `DesignGate` inne i
            # runneren. `evidence_for` er RAPPORT-stien. Jeg lukket registerhullet
            # der og lot denne staa -- saa `ADR-DOES-NOT-EXIST-999` klarerte steg
            # 7 der kjeden KJOERER, mens rapporten meldte BLOCK. Hullet var lukket
            # i speilet, ikke i gaten.
            #
            # Kommentaren under denne linja sa allerede at den FOELGER
            # `evidence_for`. Jeg fikk dem til aa divergere i samme commit som
            # skrev kommentaren om hvorfor de ikke maa det.
            "cad_status": (_resolve_ref(str(goal.get("cad_ref", "") or ""))
                           or str(ev.get("cad_status", "unknown"))),
            "adr_status": (_resolve_ref(str(goal.get("adr_ref", "") or ""))
                           or str(ev.get("adr_status", "unknown"))),
            "bl_status": str(ev.get("bl_status", "unknown")),
            "obsidian_status": str(ev.get("obsidian_status", "unknown")),
            # REVIEWER BLOCK 1. Foerste utkast skrev BARE `git` og `lease` her.
            # `BlGate` (steg 5) krever `bl`; `DesignGate` (steg 7) krever `cad` og
            # `adr`. De ble droppet — enda maalet baerer dem og `payload["goal"]`
            # kopierer dem ett dict bortenfor. Resultatet var at INGEN legitim
            # handlingssekvens kunne aapne steg 5 eller 7: alloker BL-en, aapne
            # den, mint CAD-en, mint ADR-en — fortsatt blokkert, i kode.
            #
            # Det er noeyaktig defekten `git_head` nettopp lukket (`evidence_for`
            # leste et felt ingen produsent skrev), gjenskapt for tre felter til,
            # i produsenten jeg skrev i samme commit. Muren ble flyttet, ikke
            # fjernet. `faber_observe.evidence_for` gjoer det riktig, og dette
            # foelger den.
            "source_refs": {
                k: v for k, v in (
                    ("git", str(observation.get("git_ref", ""))),
                    ("lease", ""),
                    ("cad", str(goal.get("cad_ref", "") or "")),
                    ("adr", str(goal.get("adr_ref", "") or "")),
                    ("bl", str(goal.get("bl_ref", "") or "")),
                ) if v or k == "lease"
            },
            "scope_executable": True,
            "scope_note": "",
        },
        "lease": {"paths": scope, "note": f"chain-drive {goal.get('goal_id', '')}"},
        "implement": {
            "goal_id": str(goal.get("goal_id", "")),
            "repo_root": build_root,
            "test_command": list(test_command),
        },
    }


def drive_from_observe(packet_path: str, goals_path: str, *, repo: str,
                       test_command: Sequence[str] = (),
                       limit: int = 0) -> dict:
    """A TIL AA: driv kjeden for hvert maal observasjonen sier er klart. (BL-4087)

    HULLET DETTE LUKKER. `faber_observe` og `faber_goal_state` kjoerte hvert
    tjuende minutt og MAALTE. `faber_live_adapter` kjoerte paa hver kodende
    chat-tur og RAADET. De tretten stegene -- `FaberRuntime.tick` ->
    `GovernedCodeRunner.run` -> de sju komponentene -- hadde NULL kallere:
    `--tick-json` fantes ikke i én cron-linje, én systemd-enhet eller ett
    skript. Sju oekter bygde sju komponenter, BL-4070 koblet dem sammen, og
    ingenting kalte resultatet. Dette er kalleren.

    HVOR LANGT DEN GAAR, OG HVORFOR DEN STOPPER DER.

      steg 4   preflight, mot MAALTE refs (`git_head`, scope-relativ renhet)
      steg 6   lease TATT hos autoriteten, og sluppet igjen etterpaa
      steg 8   bygg -- i en ISOLERT KOPI av HEAD, aldri i det delte treet
      tvers    skills valgt for maalet og registrert
      steg 10  STOPPER. Verdikten er PENDING, og det er ikke en mangel.

    Steg 10 er der fordi ingen har DOEMT bygget. Aa la driveren sende en PASS
    ville vaert aa skrive en post for aa faa en gate til aa slippe seg selv
    gjennom -- BL-3673, som reviewer blokkerte, gjenoppstaatt i en timer. Og
    steg 11 er utenfor uansett: `land` settes aldri (se `payload_for`), saa
    `landing_callable` tar den literale grenen og `prelanding` mangler, som
    blokkerer maalet med en navngitt grunn.

    Aa gi denne stien en reviewer og en landing er ADR-062 V5 og hard-limit #3.
    Den beslutningen bor hos Morten, ikke i et flagg her.
    """
    from agent.code_workflow import ReviewEvidence, ReviewVerdict

    packet = json.loads(Path(packet_path).expanduser().read_text(encoding="utf-8"))
    registry = json.loads(Path(goals_path).expanduser().read_text(encoding="utf-8"))
    by_id = {str(g.get("goal_id", "")): g
             for g in (registry if isinstance(registry, list) else registry.get("goals") or [])}

    driven, skipped = [], []
    for obs in packet.get("observations") or []:
        gid = str(obs.get("goal_id", ""))
        goal = by_id.get(gid)
        if goal is None:
            skipped.append({"goal_id": gid, "why": "maalet finnes ikke i registeret"})
            continue
        if not _drivable(obs.get("reasons") if "reasons" in obs else None):
            skipped.append({"goal_id": gid, "why": "blokkert av noe steg 6 ikke fjerner",
                            "reasons": list(obs.get("reasons") or [])})
            continue
        if limit and len(driven) >= limit:
            skipped.append({"goal_id": gid, "why": f"over grensen paa {limit} per tick"})
            continue

        # REVIEWER BLOCK 2, andre halvdel: PAKKEN er fra observe-tid, TREET er
        # fra drive-tid. `isolated_build_root` tar den VERIFISERTE shaen (ikke
        # live HEAD), mens
        # `source_refs["git"]`, `git_clean` og `scope_executable` baeres uendret
        # fra pakken. Observe kjoerer :20, en parallell stroem commiter, driveren
        # kjoerer paa en annen commit — og ticken registrerer provenans A mens
        # den bygger B. Det er stale-commit-klassen, og `git_clean: True` blir da
        # noeyaktig den «maalingen som er et sitat» `git_head`s egen docstring
        # advarer mot. Vi maaler paa nytt her, og hopper over med navngitt grunn
        # hvis verden har flyttet seg.
        from agent.faber_observe import git_head, scope_is_clean

        scope = str((goal.get("evidence") or {}).get("repo_scope", ""))
        live_head = git_head(repo)
        observed_head = str(obs.get("git_ref", ""))
        if not live_head or live_head != observed_head:
            skipped.append({"goal_id": gid,
                            "why": "treet har flyttet seg siden observasjonen",
                            "observed_git_ref": observed_head, "live_head": live_head})
            continue
        clean_now, dirty_now, _repo_dirty = scope_is_clean(repo, scope)
        if not clean_now:
            skipped.append({"goal_id": gid,
                            "why": "scope ikke lenger rent ved drive-tid",
                            "scope_dirty": list(dirty_now)})
            continue
        # Reviewer runde 3: rekkefoelgen var `git_head` -> `scope_is_clean` ->
        # `archive`. En commit som lander mellom de TO FOERSTE gjoer at renheten
        # ble maalt mot en annen tilstand enn den vi arkiverer. Arkiv-INNHOLDET
        # var allerede laast av `ref`-parameteren; DETTE laaser korrespondansen
        # mellom renhetsmaalingen og arkivet. Jeg hadde skrevet at forrige fiks
        # «LUKKER vinduet» — den lukket halve.
        if git_head(repo) != live_head:
            skipped.append({"goal_id": gid,
                            "why": "treet flyttet seg mens renheten ble maalt",
                            "observed_git_ref": observed_head, "live_head": live_head})
            continue

        entry_note = ""
        skills = {"coverage": "UNKNOWN", "selected": []}
        with tempfile.TemporaryDirectory(prefix="faber-drive-") as tmp:
            try:
                # Reviewer runde 3, N4: laa UTENFOR denne `try`. Reiste
                # import-linja, slapp den forbi baade denne og CLI-ens
                # `except`-tuppel -- saa ETT maals importfeil drepte hele
                # kjoeringen uten aa skrive én rapport, og de andre maalenes
                # resultater gikk tapt. En planlagt skygge-maaling som doer uten
                # rapport er en maaling man ikke faar.
                skills = skills_for_goal(obs, goal)
                # Den VERIFISERTE shaen, ikke HEAD -- se isolated_build_root.
                root = isolated_build_root(repo, tmp, live_head)
                payload = payload_for(obs, goal, repo=repo, build_root=root,
                                      test_command=test_command)
                runtime = FaberRuntime()
                evidence = lease_take(payload, PreflightInput(**payload["evidence"]))
                try:
                    result = runtime.tick(
                        FaberGoal(**payload["goal"]),
                        evidence,
                        build=build_callable(payload, runtime.runner, evidence),
                        # Verdikten er PENDING, med den MAALTE diff-id-en. Runneren
                        # blokkerer paa den, og det er svaret: ingen har doemt.
                        review=lambda b: ReviewEvidence(
                            verdict=ReviewVerdict.PENDING,
                            diff_id=str((b or {}).get("diff_id") or ""),
                            reviewer="", confidence=0.0),
                        landing=landing_callable(payload, None, LandingEvidence(
                            commit="", reviewer=ReviewVerdict.PENDING, tests="",
                            readback="", runtime_smoke="", rollback="",
                            brain_change_log="", selfstate="")),
                        prelanding_evidence=None,
                    )
                    entry = {
                        "goal_id": gid,
                        "state": result.run.goal.state.value,
                        "preflight": result.preflight.status.value,
                        "preflight_reasons": list(result.preflight.reasons),
                        "blocker": result.run.goal.blocker,
                        "gate": (result.run.handoff.required_gate
                                 if result.run.handoff else ""),
                        "next_step": result.run.goal.next_step,
                        "lease": evidence.source_refs.get("lease", ""),
                        "lease_authority": evidence.source_refs.get("lease_authority", ""),
                        "skills_selected": [x.get("name") for x in (skills.get("selected") or [])],
                        "skill_coverage": skills.get("coverage", "UNKNOWN"),
                        "build_root": f"isolert kopi av {live_head[:12]} (kastet etter ticken)",
                    }
                finally:
                    # N3: settes i `finally`, som ogsaa kjoerer naar `tick` kaster.
                    # Den ytre `except` nullstilte den foer, saa rapporten sa at
                    # leasen IKKE var sluppet naar den var det.
                    entry_note = lease_release(payload, evidence)
            except Exception as exc:  # bygget eller kopien feilet
                entry = {"goal_id": gid, "state": "ERROR",
                         "blocker": f"{type(exc).__name__}: {exc}",
                         "skills_selected": [x.get("name") for x in (skills.get("selected") or [])],
                         "skill_coverage": skills.get("coverage", "UNKNOWN")}
        entry["lease_released"] = entry_note
        driven.append(entry)

    errors = sum(1 for d in driven if d.get("state") == "ERROR")
    return {
        "artifact": "faber-chain-drive-v1",
        "errors": errors,
        "observed_at": packet.get("observed_at", ""),
        "repo": repo,
        "driven": len(driven),
        "skipped": len(skipped),
        "results": driven,
        "skipped_detail": skipped,
        "shadow": True,
        "shadow_note": (
            "Ingen landing og ingen postcommit: `land` og `postcommit` settes aldri "
            "i payloaden, og bygget skjer i en isolert kopi av den VERIFISERTE "
            "commiten, som kastes etter ticken. Det delte arbeidstreet skrives aldri til. Reviewer-verdikten er "
            "PENDING fordi ingen har doemt bygget -- ikke fordi noe manglet."),
    }

def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run one governed Faber runtime tick.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--evidence-json", help="JSON object containing PreflightInput fields")
    group.add_argument("--tick-json", help="JSON object containing goal, evidence and deterministic tick evidence")
    group.add_argument("--memory-measure-query", help="Run one real MemoryManager enforcement measurement")
    group.add_argument("--propose-job-json", help="Create one consent-first Faber cron suggestion")
    group.add_argument("--drive-observe",
                       help="Driv kjeden for hvert maal denne observe-pakken sier er klart "
                            "(skygge: bygger i isolert kopi, lander aldri)")
    parser.add_argument("--goals", default="~/.hermes-gui/faber/goals.json")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--test-command", default="")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    try:
        if args.drive_observe:
            report = drive_from_observe(
                args.drive_observe, args.goals, repo=args.repo,
                test_command=tuple(args.test_command.split()) if args.test_command else (),
                limit=args.limit)
            print(json.dumps(report, default=str, ensure_ascii=False))
            # Reviewer runde 3: returnerte 0 ubetinget, saa «0 drevet, 7 ERROR»
            # og «alt gikk bra» hadde samme exit-kode. En scheduler leser
            # exit-koden, ikke JSON-en.
            return 2 if report.get("errors") else 0
        if args.propose_job_json:
            from agent.faber_tui_egress import propose_faber_job
            record = propose_faber_job(**json.loads(args.propose_job_json))
            print(json.dumps({"status": "pending" if record else "deduplicated_or_capped", "record": record}, default=str))
            return 0 if record else 2
        if args.memory_measure_query:
            from agent.continuous_pipeline import CANONICAL_MEMORY_LAYER_IDS, MemoryLayerSpec, MemoryManagerBridge, MemoryScheduler
            from agent.memory_manager import MemoryManager
            bridge = MemoryManagerBridge(
                MemoryManager(),
                MemoryScheduler(tuple(MemoryLayerSpec(layer_id, "symbiose.canonical") for layer_id in CANONICAL_MEMORY_LAYER_IDS), require_canonical=True),
                strict=True,
                metrics_path=os.path.expanduser("~/.hermes-gui/faber/memory-enforcement.json"),
                source_scope="faber.codex",
            )
            hook = bridge.before_turn(args.memory_measure_query, phase="sense")
            print(json.dumps({"status": "OK", "selection": asdict(hook.selection), "source_scope": hook.source_scope, "metrics_path": str(bridge.metrics_path)}))
            return 0
        if args.evidence_json:
            evidence = PreflightInput(**json.loads(args.evidence_json))
            result = FaberRuntime().preflight_gate.evaluate(evidence)
            print(json.dumps({"status": result.status.value, "reasons": result.reasons, "evidence": asdict(result.evidence)}))
            return 0 if result.status.value == "PASS" else 2
        payload = json.loads(args.tick_json)
        goal = FaberGoal(**payload["goal"])
        evidence = PreflightInput(**payload["evidence"])
        review = ReviewEvidence(**payload["review"])
        landing = LandingEvidence(**payload["landing"])
        prelanding = LandingEvidence(**payload["prelanding"]) if payload.get("prelanding") else None
        runtime = FaberRuntime()
        # STEG 6 FOERST. Se lease_take: claimet maa skje foer BAADE
        # `build_callable` og gaten, ellers binder de seg til hvert sitt
        # lease-sett, og hverken steg 4 eller steg 11 beviser noe.
        #
        # OG DET MAA STAA I EN `try/finally`. Reviewer runde 2, BLOCK 1: claimet
        # skjer her, men `build_callable`, `landing_callable` og
        # `postcommit_callable` evalueres som ARGUMENTER til `tick(...)` — altsaa
        # ETTER claimet — og hver av dem kan kaste `ValueError` paa en ugyldig
        # spec. Den `except`-en nederst fanget det og returnerte 2, rett forbi
        # `lease_release`. Maalt, med claim/release instrumentert:
        #
        #     exactly-one-brudd   rc=2  claimed=[('a.py',)]  released=[]
        #     manglende testmaal  rc=2  claimed=[('a.py',)]  released=[]
        #
        # Begge de to stiene er NYE i denne runden: de er BLOCK 1- og BLOCK
        # 4-fiksene selv. Altsaa gjenopprettet wiringen som skulle lukke trap 3
        # i `lease_authority` noeyaktig trap 3 — en foreldreloes lease til TTL
        # (3600 s), uten et ord om det i rapporten.
        evidence = lease_take(payload, evidence)
        # ÉN rapport per kjoering. Foerste utkast printet slipp-noten som et EGET
        # JSON-objekt fra `finally`, saa rekkefoelgen inverterte: paa suksess kom
        # verdikten foerst, paa avbrudd kom noten foerst. En kaller som leser
        # «det foerste JSON-objektet» ville faatt ulike ting paa de to stiene.
        # (Og jeg beskrev min egen fiks feil: suksess-stien bar ALDRI noten i
        # rapporten — reviewer leste koden, jeg leste hukommelsen min.)
        rc = 2
        report: dict[str, object] = {
            "status": "BLOCK", "reasons": ["ticken avbroet foer den rakk aa rapportere"]}
        try:
            rc, report = _run_tick(payload, goal, evidence, review, landing, prelanding, runtime)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            report = {"status": "BLOCK", "reasons": [f"invalid tick payload: {exc}"]}
        finally:
            note = lease_release(payload, evidence)
            if note:
                report["lease_released"] = note
            print(json.dumps(report, default=str))
        return rc
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCK", "reasons": [f"invalid tick payload: {exc}"]}))
        return 2


def _run_tick(payload, goal, evidence, review, landing, prelanding, runtime,
              ) -> tuple[int, dict[str, object]]:
    """Selve ticken. Skilt ut saa `lease_release` kan staa i en `finally`.

    Returnerer `(exit-kode, rapport)` og printer ingenting: kalleren eier
    utskriften, slik at slipp-noten og verdikten blir ETT objekt.
    """
    observed = LandingObservation()
    result = runtime.tick(
        goal,
        evidence,
        build=build_callable(payload, runtime.runner, evidence),
        review=lambda _: review,
        landing=landing_callable(payload, prelanding, landing, observed=observed),
        prelanding_evidence=prelanding,
        postcommit=postcommit_callable(payload, observed),
    )
    # BLOCK 3. Foer dette ble `postcommit_result` kastet: en tick der steg
    # 12/13 FEILET skrev `{"status": "landed", "reasons": []}` og returnerte
    # 0. En stille utelatelse av tilbakelesingen — samme form som
    # `{"postcommit": {}}`-defekten, ett lag lenger ut.
    report = {
        "status": result.run.goal.state.value,
        "preflight": result.preflight.status.value,
        "reasons": result.run.handoff.blocker if result.run.handoff else [],
    }
    postcommit_requested = "postcommit" in payload
    if postcommit_requested:
        pc = result.postcommit
        report["postcommit"] = {
            "success": bool(pc and pc.success),
            "error": (pc.error if pc else "steg 12/13 ble bedt om, men kjoerte ikke: "
                                          "maalet naadde aldri LANDED"),
            "missing": list(pc.missing) if pc else [],
            "executed": list(pc.executed) if pc else [],
            "replayed": list(pc.replayed) if pc else [],
        }
    landed_ok = result.run.goal.state.value in {"verified", "landed", "measured", "learned"}
    if postcommit_requested and not (result.postcommit and result.postcommit.success):
        return 2, report
    return (0 if landed_ok else 2), report


if __name__ == "__main__":
    raise SystemExit(_cli())
