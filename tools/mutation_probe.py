#!/usr/bin/env python3
"""Mutasjonsprobe: fjern ett vern om gangen, og krev at en navngitt test blir roed.

BL-4051. Daekker BL-4029 steg 11 (vakten `LandingScopeGate`) og BL-4051
(handen `GitLandingExecutor`).

En groenn testsuite sier at kodens NAAVAERENDE oppfoersel er beskrevet. Den sier
ingenting om hvorvidt vernene BAERER noe. Denne proben svarer paa det ene
spoersmaalet: hvis jeg fjerner dette vernet, merker noen det? Overlever en mutant,
maaler den tilhoerende testen ingenting -- uansett hvor godt den leser.

KJOERER I EN ISOLERT KOPI, ALDRI I DET DELTE ARBEIDSTREET
---------------------------------------------------------
Foerste versjon muterte filene paa plass i arbeidstreet, med backup ->
muter -> kjoer -> gjenopprett. Det var galt, og feilen er samme klasse som
modulen proben tester:

1. GJENOPPRETTINGEN KAN KLOBBE EN SAMTIDIG SKRIVER. `agent/code_workflow.py`
   bar +457 ukommitterte linjer fra en parallell stroem (BL-4052) mens dette ble
   skrevet. Hadde de lagret fila inne i mutasjonsvinduet, ville gjenopprettingen
   stille ha tilbakestilt lagringen deres.

2. TO SAMTIDIGE KJOERINGER GIR FALSKT BEVIS. Reviewer-agenten kjoerte proben mot
   de samme filene samtidig som forfatteren. MAALT, med direkte evidens: en kopi
   tatt av `agent/faber_landing.py` inne i det vinduet inneholdt en MUTANT
   (`return tuple(added)`), og to urelaterte tester feilet «uforklarlig». Et
   mutasjonsresultat som avhenger av hvem andre som kjoerer er ikke evidens.

Loesningen er den samme som handen selv bruker: ikke stol paa at ingen andre
roerer noe -- gjoer det umulig. `git archive HEAD` er en ren LESING av det delte
repoet, og alt skriv skjer i en `TemporaryDirectory`.

OM PYTHONDONTWRITEBYTECODE
--------------------------
Underveis fantes ogsaa en hypotese om at raske muter/gjenopprett-sykluser lot
pytest kjoere foreldet bytekode, fordi `__pycache__` valideres paa parret
(kildens mtime i hele sekunder, kildens stoerrelse). Den ble stoettet av et
korrelasjonelt eksperiment, men den uavhengige variabelen -- den andre samtidige
kjoeringen -- var ikke kontrollert for, og reviewer trakk selv diagnosen tilbake
som «et sammenfall». Den ER ikke bekreftet som aarsak her.

Flagget staar likevel, fordi kostnaden er null og skaden det kunne forhindret er
den verste sorten: en mutant rapportert DREPT som i virkeligheten ble drept av en
ANNEN mutants bytekode. Det er en usann PASS, og en usann PASS i et
maaleinstrument forplanter seg til alt instrumentet brukes til aa hevde.

TO PORTER, IKKE EN
------------------
1. GRUNNLINJEN MAA VAERE GROENN. Et mutasjonsresultat maalt over en roed
   grunnlinje er meningsloest: man vet ikke om en «drept» mutant ble drept av
   mutasjonen eller av det som allerede var i stykker.

2. TESTNODEN MAA FINNES FOER MUTASJONEN. Dette er den viktigere, og den ble
   lagt til etter at proben tok seg selv i loegn. `MAY_BE_UNLANDED` kopierte
   inn arbeidstre-filer KUN hvis `git archive` ikke hadde levert dem. Da
   `tests/test_faber_landing.py` landet, sluttet kopieringen -- og den isolerte
   kopien fikk HEADs testfil med 39 tester i stedet for arbeidstreets 41.
   Mutanten som pekte paa en av de to nye testene kjoerte da mot en test som
   IKKE FANTES: pytest svarer «ERROR: not found» med exit 4, drapskriteriet er
   `returncode == 0`, og proben meldte «drept». MAALT: den meldte drept ogsaa
   uten mutasjon, og ogsaa med `agent/faber_runtime.py` slettet.

   En groenn grunnlinje for hele fila fanger ikke dette -- den sier ingenting om
   hvorvidt EN navngitt node finnes. Derfor kjoeres `--collect-only` paa noden
   foer hver mutasjon, og en node som ikke lar seg samle telles som OVERLEVER.

3. DRAPET MAA VAERE ET NAVNGITT TESTFALL. Node-porten lukket bare den ene halvdelen
   av samme forveksling. Den andre: en mutasjon som gjoer modulen UIMPORTERBAR gir
   ogsaa exit != 0, uten at testen har kjoert i det hele tatt. MAALT med en
   bevisst oedelagt `class FaberRuntime(`: proben meldte «ok ... alle 1 mutanter
   ble drept», exit 0.

   `returncode == 0` er for svakt som drapskriterium i BEGGE retninger. Kravet er
   naa exit NOEYAKTIG 1 OG at `FAILED <fil>::<test>` staar i utdata -- altsaa at
   akkurat den navngitte testen feilet, ikke at «noe gikk galt». Verifisert mot
   alle mutantene: hver enkelt gir et ekte, navngitt testfall.

HVA SOM MAALES I HVILKEN TILSTAND
---------------------------------
Filene denne endringen selv roerer (`OVERLAY`) legges inn fra ARBEIDSTREET --
det er den tilstanden som er i ferd med aa landes, og altsaa den som skal maales.
Alt annet maales ved HEAD. Det er bevisst: `agent/code_workflow.py` og
`agent/faber_runtime.py` baerer akkurat naa ukommitterte linjer fra parallelle
stroemmer (BL-4052, BL-4050), og et bevis som hviler paa en annen stroems
halvferdige arbeid er ikke et bevis om denne endringen.

Bruk:
    .venv/bin/python tools/mutation_probe.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = os.environ.get("HERMES_PYTHON", sys.executable)

GATE = "agent/code_workflow.py"
HAND = "agent/faber_landing.py"
RUNTIME = "agent/faber_runtime.py"
T_GATE = "tests/test_code_workflow.py"
T_HAND = "tests/test_faber_landing.py"
#: BL-4070 — soemmene mellom kjedens inngang og de sju komponentene.
BRIDGE = "agent/faber_control_bridge.py"
T_SEAM = "tests/test_chain_seam_wiring.py"
T_GUARD = "tests/test_chain_is_wired.py"
#: BL-4070 D1-D3: de tre defektene en LIVE bro-kjoering fant.
AUTHORITY = "agent/lease_authority.py"
CLASSIFIER = "agent/task_classifier.py"
T_AUTHORITY = "tests/test_lease_authority.py"

#: Filene hvis ARBEIDSTRE-tilstand er det som maales. Legges ALLTID over det
#: `git archive` leverte -- ikke bare naar de mangler. Den tidligere
#: «kopier hvis fraevaerende»-regelen sluttet stille aa virke i det oeyeblikket
#: filene landet, og gjorde en mutant vakuoes uten aa si fra. Se docstringen.
#: BL-4070: RUNTIME, BRIDGE og T_SEAM maa ogsaa legges over. Uten dem leser
#: proben HEADs versjon av soemmene, og en mutant mot en linje som ikke finnes
#: i kopien er ikke et drap -- det er en maaling av ingenting. Porten under
#: (`source.count(anchor) != 1`) fanger det som overlever, ikke som seier.
#:
#: HISTORIKK, OG DEN ER UTLOEPT — MED VILJE BEHOLDT SOM EKSEMPEL. Mens BL-4070
#: ble skrevet var grunnlinjen ROED i det delte arbeidstreet, fordi `T_HAND`
#: ble lagt over fra et tre der BL-4055 hadde tester som krevde
#: `GovernedCodeRunner(second_opinion=...)` — en parameter som bare fantes i
#: DERES ulandede `code_workflow.py`. BL-4055 landet som `5a9a6547c`, og
#: tilstanden loeste seg selv slik den skulle. Reviewer maalte etterpaa:
#: grunnlinje groenn, 43 av 43 drept, med den EKTE overlay-lista.
#:
#: Den forrige versjonen av dette avsnittet sa «OG DET GJELDER FORTSATT NAAR
#: DU LESER DETTE» om en maaling som var timer gammel. En kommentar som
#: paastaar en LEVENDE maaling den ikke lenger har, er samme defektklasse som
#: proben jakter paa. Skriv maalinger med dato og utfall, aldri i presens.
OVERLAY = (HAND, T_HAND, RUNTIME, BRIDGE, T_SEAM, T_GUARD,
           AUTHORITY, CLASSIFIER, T_AUTHORITY)

#: (navn, fil, anker, erstatning, testfil, testen som MAA bli roed)
MUTANTS: tuple[tuple[str, str, str, str, str, str], ...] = (
    # --- vakten: BL-4029 steg 11 ---
    ("VAKT tomt landingssett slipper gjennom", GATE,
     "        if not landing:\n            reasons.append(",
     "        if False:\n            reasons.append(",
     T_GATE, "test_an_empty_landing_set_blocks_because_unknown_is_not_empty"),
    ("VAKT delmengde-sjekken droppes", GATE,
     "        outside = sorted(landing - leased)\n        if outside:",
     "        outside = sorted(landing - leased)\n        if False:",
     T_GATE, "test_the_ae832c8a4_sweep_is_blocked"),
    ("VAKT tomt lease-sett slipper gjennom", GATE,
     '        if not leased:\n            reasons.append("lease set is empty',
     '        if False:\n            reasons.append("lease set is empty',
     T_GATE, "test_an_empty_lease_set_blocks"),

    # --- porten selv: diskriminerer den, eller er den bare wiret? ---
    ("VAKT preflight krever ingen refs (porten slutter aa skille)", GATE,
     '    REQUIRED_REFS: tuple[str, ...] = ("git", "lease")',
     "    REQUIRED_REFS: tuple[str, ...] = ()",
     T_HAND, "test_the_runtime_tick_blocks_at_preflight_before_the_hand_is_reachable"),

    # --- handen: selve commit-formen ---
    ("HAND --only fjernes fra commit", HAND,
     'git commit -m "$msg" --only -- "$@" >"$d/out" 2>&1 || exit 1',
     'git commit -m "$msg" >"$d/out" 2>&1 || exit 1',
     T_HAND, "test_the_218_file_sweep_cannot_happen_here"),
    ("HAND -N fjernes fra staging", HAND,
     '["git", "add", "-N", "--", *untracked],',
     '["git", "log", "-1", "--format=%H"],',
     T_HAND, "test_a_new_file_lands_which_only_works_because_of_add_N"),
    ("HAND returkoden fra add -N ignoreres", HAND,
     "        if proc.returncode != 0:",
     "        if False:",
     T_HAND, "test_a_locked_index_is_diagnosed_as_a_locked_index"),

    # --- handen: etterkontrollen ---
    ("HAND fremmede filer ignoreres", HAND,
     "        if foreign:\n            reasons.append(",
     "        if False:\n            reasons.append(",
     T_HAND, "test_verification_names_a_foreign_file_that_came_along"),
    ("HAND innholdsdrift ignoreres", HAND,
     "            elif after != before:",
     "            elif False:",
     T_HAND, "test_verification_catches_content_written_under_us"),
    ("HAND emnelinje-kontrollen droppes", HAND,
     "        if subject and landed_subject and landed_subject != subject:",
     "        if False:",
     T_HAND, "test_a_commit_that_is_not_ours_is_caught_by_its_subject"),
    ("HAND -z fjernes fra diff-tree (filnavn blir sitert)", HAND,
     'git diff-tree --no-commit-id --name-only -r --root -z "$sha" >"$d/files"',
     'git diff-tree --no-commit-id --name-only -r --root "$sha" >"$d/files"',
     T_HAND, "test_a_non_ascii_filename_lands_and_verifies"),

    # --- handen: stivalidering ---
    ("HAND kataloger tillates som sti", HAND,
     "            if resolved.is_dir():",
     "            if False:",
     T_HAND, "test_a_directory_refuses_because_git_expands_it_to_every_file_beneath"),
    ("HAND unormaliserte stavemaater tillates", HAND,
     "            if str(PurePosixPath(path)) != path:",
     "            if False:",
     T_HAND, "test_an_unnormalised_spelling_refuses_before_git_rewrites_it"),

    # --- handen: feil mens vi roerer delt tilstand ---
    ("HAND tidsavbrudd kastes videre (foreldreloes commit mistes)", HAND,
     "        except (subprocess.SubprocessError, OSError) as exc:",
     "        except ValueError as exc:",
     T_HAND, "test_a_git_that_never_reports_back_still_names_the_commit_that_may_exist"),
    ("HAND intent-to-add ryddes ikke etter feilet commit", HAND,
     "        if not ok:\n            self._undo_our_intent_to_add(added)\n            return LandingResult(",
     "        if not ok:\n            return LandingResult(",
     T_HAND, "test_a_failed_commit_leaves_no_intent_to_add_in_the_shared_index"),
    ("HAND oppryddingen skiller ikke vaare i-t-a fra andres stagede", HAND,
     "            return tuple(path for path in added if path not in really_staged)",
     "            return tuple(added)",
     T_HAND, "test_the_cleanup_never_discards_another_streams_staged_content"),
    ("HAND oppryddingen skiller ikke (andres GENUINT TOMME fil)", HAND,
     "            return tuple(path for path in added if path not in really_staged)",
     "            return tuple(added)",
     T_HAND, "test_the_cleanup_leaves_even_an_empty_file_another_stream_staged"),

    # --- handen: emnelinja ---
    ("HAND emnet leses som splitlines()[0] i stedet for som git %s", HAND,
     '    first = re.split(r"\\n\\s*\\n", message.strip(), maxsplit=1)[0]\n    return " ".join(first.split())',
     "    return message.splitlines()[0]",
     T_HAND, "test_ordinary_multiline_messages_are_not_mistaken_for_someone_elses_commit"),
    ("HAND git-siden av emnet normaliseres ikke", HAND,
     '        landed_subject = " ".join(landed_subject.split())',
     "        landed_subject = landed_subject",
     T_HAND, "test_ordinary_multiline_messages_are_not_mistaken_for_someone_elses_commit"),

    # --- kjeden: gir ticken virkelig handen videre, og overlever avslaget? ---
    ("KJEDE handoffen skrives ikke naar landingen nektes", RUNTIME,
     "        if result.handoff is not None and self.handoff_store is not None:",
     "        if False:",
     T_HAND, "test_the_runtime_tick_blocks_and_persists_a_handoff_when_the_hand_refuses"),
    ("KJEDE ticken ekkoer evidensen i stedet for aa utfoere landingen", RUNTIME,
     "            landing=landing,",
     "            landing=lambda _: prelanding_evidence,",
     T_HAND, "test_the_runtime_tick_lands_through_the_executor"),

    # --- BL-4070 STEG 6: er det AUTORITETENS svar som blir kjedens lease-sett? ---
    ("SOEM steg 6 beholder payloadens lease-sett", RUNTIME,
     '    refs["lease"] = ",".join(outcome.acquired) if outcome.ok else ""',
     '    refs["lease"] = str(evidence.source_refs.get("lease", ""))',
     T_SEAM, "test_authority_answer_replaces_the_payloads_lease_set"),
    ("SOEM steg 6 melder klart selv naar claimet feilet", RUNTIME,
     "    return replace(evidence, lease_clear=bool(outcome.ok), source_refs=refs)",
     "    return replace(evidence, lease_clear=True, source_refs=refs)",
     T_SEAM, "test_failed_claim_clears_the_lease_set_and_the_flag"),

    # --- BL-4070 STEG 11: kalles handen, eller ekkoes literalen? ---
    ("SOEM steg 11 faller alltid tilbake paa literalen", RUNTIME,
     '    if "land" not in payload:\n        return lambda _: literal',
     "    if True:\n        return lambda _: literal",
     T_SEAM, "test_the_hand_is_called_with_the_judged_set_and_the_measured_answer_wins"),
    ("SOEM steg 11 registrerer ikke den maalte landingen", RUNTIME,
     "        observed.evidence = result\n        return result",
     "        return result",
     T_SEAM, "test_the_hand_is_called_with_the_judged_set_and_the_measured_answer_wins"),

    # --- BL-4070 STEG 12/13: leses commiten tilbake mot det MAALTE settet? ---
    ("SOEM steg 13 godtar en tom observasjon", RUNTIME,
     "        if landed is None:",
     "        if False:",
     T_SEAM, "test_postcommit_refuses_when_no_hand_measured_a_landing"),
    ("SOEM steg 13 leser tilbake mot payloadens filsett", RUNTIME,
     "        expected = tuple(landed.landing_set or ())",
     '        expected = tuple(spec.get("expected_files") or ("payload/said.py",))',
     T_SEAM, "test_postcommit_reads_back_against_the_measured_set_not_the_payloads"),

    # --- BL-4070: naervaer, ikke sannhetsverdi ---
    ("SOEM tom postcommit-spec hopper stille over steg 12/13", RUNTIME,
     '    if "postcommit" not in payload:\n        return None',
     '    if not payload.get("postcommit"):\n        return None',
     T_SEAM, "test_empty_postcommit_object_is_an_error_not_a_silent_skip"),

    # --- BL-4070 BROEN: overlever UVERIFISERT som egen verdi? ---
    ("SOEM broen flater UVERIFISERT ut til «ikke ren»", BRIDGE,
     '    return {"clear": clear, "paths": list(paths), "note": note}',
     '    return {"clear": bool(clear), "paths": list(paths), "note": note}',
     T_SEAM, "test_bridge_keeps_unverified_distinct_from_not_clear"),
    ("SOEM broen paastaar fravaer for et maal uten tekst", BRIDGE,
     "    if not text:",
     "    if False:",
     T_SEAM, "test_bridge_never_claims_absence_for_a_textless_goal"),

    # --- BL-4070 runde 2: de fire reviewer-BLOCKene, som mutanter ---
    ("SOEM steg 12 slipper igjennom uten kjoeretidssvar", RUNTIME,
     "    if bool(container) == bool(no_runtime_target):",
     "    if False:",
     T_SEAM, "test_postcommit_requires_exactly_one_runtime_answer"),
    ("SOEM steg 12/13 godtar fravaer av testmaal", RUNTIME,
     "    if not test_paths:\n        raise ValueError(",
     "    if False:\n        raise ValueError(",
     T_SEAM, "test_postcommit_requires_a_test_target"),
    ("SOEM steg 12/13 stoler paa LANDED uten aa se etter", RUNTIME,
     "        if result.goal.state is not GoalState.LANDED:",
     "        if False:",
     T_SEAM, "test_postcommit_refuses_on_a_goal_that_never_landed"),
    ("SOEM tom implement-spec reverterer stille til literalen", RUNTIME,
     '    if "implement" in payload:',
     '    if payload.get("implement"):',
     T_SEAM, "test_empty_implement_object_cannot_silently_revert_step_8"),
    ("SOEM ticken slipper ikke leasen den tok", RUNTIME,
     "        ok, note = release(held)",
     '        ok, note = True, "sluppet"',
     T_SEAM, "test_the_tick_releases_what_it_took"),
    ("VAKT ser ikke `from agent import X`", T_GUARD,
     '            elif node.module == "agent":',
     "            elif False:",
     T_SEAM, "test_the_guard_sees_from_agent_import_x"),

    # --- BL-4070 D1: svarer aggregatet paa spoersmaalet det sier det svarer paa? ---
    ("D1 dybden regnes kun over maal som STOPPET", BRIDGE,
     '    reached = [g["reached_step"] for g in per_goal if g["reached_step"]]',
     '    reached = [g["stopped_at_step"] for g in per_goal if g["stopped_at_step"]]',
     T_SEAM, "test_d1_a_goal_that_never_stopped_still_counts_toward_the_depth"),
    ("D1 NOT_EXECUTED telles som naadd", BRIDGE,
     '             if s["status"] == DryRunStatus.PLANNED.value and s["number"]),',
     '             if s["number"]),',
     T_SEAM, "test_d1_reached_step_never_counts_a_not_executed_step_as_reached"),

    # --- BL-4070 D2: én parser, ikke to ---
    ("D2 autoriteten smalner igjen til .py", AUTHORITY,
     '_SCOPE_PATH = re.compile(r"^[\\w./-]+\\.(?:py|ts|tsx|js|json|ya?ml|md|sh|service|plist)$")',
     '_SCOPE_PATH = re.compile(r"^[\\w./-]+\\.py$")',
     T_SEAM, "test_d2_a_non_python_scope_is_now_askable"),
    ("D2 broen faar sin egen parser tilbake", BRIDGE,
     "    from agent.lease_authority import scope_paths\n\n    return tuple(scope_paths(scope))",
     "    return tuple(x for x in re.split(r\"[,\\s]+\", scope) if x.endswith(\".py\"))",
     T_SEAM, "test_d2_the_two_scope_parsers_are_now_one"),

    # --- BL-4070 D3: MWPs eget navnerom ---
    ("D3 ADR-MWP-formen fjernes", CLASSIFIER,
     '    (re.compile(r"^ADR-(?:HERMES|TRUTH|MWP|H\\d+)-[A-Z0-9][A-Z0-9.-]*\\b",\n'
     '                re.IGNORECASE | re.ASCII), "ADR-MWP"),',
     "",
     T_SEAM, "test_d3_mwp_contract_refs_are_a_named_form_not_a_missing_one"),
    ("D3 registrene slaas sammen til ett", CLASSIFIER,
     '                re.IGNORECASE | re.ASCII), "ADR-MWP"),',
     '                re.IGNORECASE | re.ASCII), "ADR"),',
     T_SEAM, "test_d3_the_two_registers_do_not_merge"),
    ("D3 utvidelsen godtar et bart prefiks", CLASSIFIER,
     '    (re.compile(r"^BL-(?:HERMES|MWP)-[A-Z0-9][A-Z0-9.-]*\\b",',
     '    (re.compile(r"^BL-(?:HERMES|MWP)",',
     T_SEAM, "test_d3_a_bare_namespace_prefix_still_buys_nothing"),

    # --- reviewer runde 2: de to BLOCKene, som mutanter ---
    ("R2 leasen slippes ikke naar ticken avbryter", RUNTIME,
     "        finally:\n            note = lease_release(payload, evidence)",
     "        finally:\n            note = \"\"",
     T_SEAM, "test_the_cli_never_leaks_a_lease_on_any_abort_path[exactly-one-brudd-extra0]"),
    ("R2 signaturvakten leser tilbake den patchede faken", T_SEAM,
     "    fakes = _fake_adapters(monkeypatch, apply=False)",
     "    fakes = _fake_adapters(monkeypatch)",
     T_SEAM, "test_every_faked_adapter_matches_the_real_signature"),

    # --- reviewer runde 4: de to sistene ---
    ("R4 broen returnerer en literal i stedet for aa spoerre selektoren", BRIDGE,
     "    selection = select_for_task(text, stage=\"bridge:cross\")\n    return selection.to_json()",
     '    return {"queryable": True, "coverage": "UNKNOWN", "selected": []}',
     T_SEAM, "test_bridge_hands_the_selector_the_goals_text_and_the_right_stage"),
    # Reviewer runde 5: foerste versjon SLETTET linja og drepte via NameError —
    # et proxy-drap, ikke defektens form. Denne FLYTTER den tilbake under claimet,
    # noeyaktig slik runde 3-defekten saa ut.
    ("R4 claim-vinduet aapnes igjen (refs under claim)", RUNTIME,
     '    refs = dict(evidence.source_refs)\n'
     '    outcome = claim(paths, ttl=int(spec.get("ttl") or DEFAULT_TTL),\n'
     '                    note=str(spec.get("note") or ""))',
     '    outcome = claim(paths, ttl=int(spec.get("ttl") or DEFAULT_TTL),\n'
     '                    note=str(spec.get("note") or ""))\n'
     "    refs = dict(evidence.source_refs)",
     T_SEAM,
     "test_the_cli_never_leaks_a_lease_on_any_abort_path[source_refs er ikke en mapping-extra5]"),
)


def isolated_copy(into: Path) -> None:
    """HEAD-treet, med arbeidstre-versjonen av de maalte filene lagt over.

    Ren LESING av det delte repoet: `git archive` og `shutil.copy` fra kilden,
    alt skriv i `into`.
    """
    archive = subprocess.run(["git", "archive", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, timeout=300)
    if archive.returncode != 0:
        raise SystemExit(f"git archive feilet: {archive.stderr.decode()[:300]}")
    tar = subprocess.run(["tar", "-x", "-C", str(into)], input=archive.stdout,
                         capture_output=True, timeout=300)
    if tar.returncode != 0:
        raise SystemExit(f"tar feilet: {tar.stderr.decode()[:300]}")
    for rel in OVERLAY:
        destination = into / rel
        # F4: katalogen finnes ikke naar fila er helt ny og ikke i HEAD.
        destination.parent.mkdir(parents=True, exist_ok=True)
        # copy, ikke copy2: mtime skal vaere NAA, aldri kildens.
        shutil.copy(REPO_ROOT / rel, destination)


def main() -> int:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    pytest_base = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"]

    with tempfile.TemporaryDirectory(prefix="mutation-probe-") as tmp:
        repo = Path(tmp)
        isolated_copy(repo)
        print(f"isolert kopi: {repo}  (det delte arbeidstreet roeres ikke)")

        baseline = subprocess.run([*pytest_base, T_HAND, T_GATE, T_SEAM], cwd=str(repo),
                                  capture_output=True, text=True, timeout=1800, env=env)
        if baseline.returncode != 0:
            print("GRUNNLINJEN ER ROED — et mutasjonsresultat maalt over den betyr ingenting:")
            # stderr maa med: er `PY` en interpreter uten pytest, er stdout TOM, og
            # en tom feilmelding er den slags «avslag uten grunn» proben ellers
            # blokkerer paa. Vanligste aarsak: kjoert med system-python i stedet
            # for .venv/bin/python.
            said = ((baseline.stdout or "") + (baseline.stderr or "")).strip()
            print(said[-1500:] or f"(ingen utdata fra {PY} -m pytest)")
            return 1
        print(f"grunnlinje groenn: {(baseline.stdout or '').strip().splitlines()[-1]}\n")

        survivors: list[str] = []
        for name, rel, anchor, replacement, testfile, expect in MUTANTS:
            collectable = subprocess.run(
                [*pytest_base, "--collect-only", f"{testfile}::{expect}"], cwd=str(repo),
                capture_output=True, text=True, timeout=300, env=env)
            if collectable.returncode != 0:
                # Uten denne porten leser proben pytests «not found» (exit 4) som
                # et drap. En mutant som peker paa en test som ikke finnes maaler
                # ingenting, og maa telle som overlever -- ikke som seier.
                print(f"  ?? {name}: {expect} lar seg ikke samle i kopien — maaler ingenting")
                survivors.append(name)
                continue
            target = repo / rel
            source = target.read_text(encoding="utf-8")
            if source.count(anchor) != 1:
                print(f"  ?? {name}: ankeret finnes {source.count(anchor)} ganger — ikke entydig")
                survivors.append(name)
                continue
            target.write_text(source.replace(anchor, replacement, 1), encoding="utf-8")
            try:
                proc = subprocess.run([*pytest_base, f"{testfile}::{expect}"], cwd=str(repo),
                                      capture_output=True, text=True, timeout=1800, env=env)
                said = (proc.stdout or "") + (proc.stderr or "")
                if proc.returncode == 0:
                    print(f"  XX {name}: testen ble GROENN uten vernet -> den maaler ingenting")
                    survivors.append(name)
                elif proc.returncode != 1 or f"FAILED {testfile}::{expect}" not in said:
                    # Exit != 0 er ikke det samme som «testen feilet». En mutasjon
                    # som knekker importen gir ogsaa exit != 0, uten at testen har
                    # kjoert. Da er mutanten ubevist, ikke drept.
                    print(f"  XX {name}: ikke et navngitt testfall (exit {proc.returncode})"
                          f" -> maaler ingenting")
                    survivors.append(name)
                else:
                    print(f"  ok {name}")
            finally:
                target.write_text(source, encoding="utf-8")

        print()
        if survivors:
            print(f"MUTASJONSPROBE FEILET — {len(survivors)} overlevde: " + "; ".join(survivors))
            return 1
        print(f"MUTASJONSPROBE: alle {len(MUTANTS)} mutanter ble drept.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
