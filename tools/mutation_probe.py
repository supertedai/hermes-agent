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

#: Filene hvis ARBEIDSTRE-tilstand er det som maales. Legges ALLTID over det
#: `git archive` leverte -- ikke bare naar de mangler. Den tidligere
#: «kopier hvis fraevaerende»-regelen sluttet stille aa virke i det oeyeblikket
#: filene landet, og gjorde en mutant vakuoes uten aa si fra. Se docstringen.
OVERLAY = (HAND, T_HAND)

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

        baseline = subprocess.run([*pytest_base, T_HAND, T_GATE], cwd=str(repo),
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
