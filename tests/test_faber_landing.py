"""BL-4051 steg 11: utføreren, målt mot ekte git.

Testene her kjører mot ekte repoer i tmp_path, ikke mot mocks. Det er ikke
pedanteri: hele modulen hviler på hva ``git commit --only`` faktisk gjør med en
forurenset indeks, og en mock ville bare gjentatt min egen antakelse om det
tilbake til meg. Antakelsen er nettopp det som må måles.
"""
from __future__ import annotations

import ast
import inspect
import json
import re
import subprocess
from pathlib import Path

import pytest

from agent.code_workflow import (
    FaberGoal,
    GoalState,
    GovernedCodeRunner,
    LandingEvidence,
    PreflightInput,
    PreflightResult,
    PreflightStatus,
    ReviewEvidence,
    ReviewVerdict,
)
from agent.faber_landing import (
    GitLandingExecutor,
    landing_callable,
)


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=60)
    return (proc.stdout or proc.stderr).strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", ".")
    git(root, "config", "user.email", "faber@test")
    git(root, "config", "user.name", "faber")
    git(root, "config", "commit.gpgsign", "false")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "base.txt")
    git(root, "commit", "-qm", "init")
    return root


def executor(repo: Path, tmp_path: Path, **kw) -> GitLandingExecutor:
    return GitLandingExecutor(repo, record_path=tmp_path / "landings.jsonl", **kw)


def committed_files(repo: Path, ref: str = "HEAD") -> list[str]:
    out = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", ref)
    return sorted(x for x in out.splitlines() if x.strip())


def hook(repo: Path, name: str, body: str) -> None:
    path = repo / ".git" / "hooks" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


# --------------------------------------------------------- selve sveipet ---

def test_the_218_file_sweep_cannot_happen_here(repo, tmp_path):
    """2026-08-10, målt: én bar `git commit` tok 218 fremmede filer.

    Dette er den samme situasjonen, gjenskapt: en delt indeks full av en annen
    strøms stagede arbeid, pluss en modifisert sporet fil i arbeidstreet. Det som
    skal lande er ÉN fil.
    """
    for i in range(218):
        (repo / f"foreign_{i}.txt").write_text(f"foreign {i}\n", encoding="utf-8")
    git(repo, "add", *[f"foreign_{i}.txt" for i in range(218)])
    (repo / "base.txt").write_text("base\nendret av en annen strøm\n", encoding="utf-8")
    (repo / "mine.py").write_text("x = 1\n", encoding="utf-8")

    result = executor(repo, tmp_path).land(["mine.py"], "BL-4051: kun min fil")

    assert result.ok, result.reasons
    assert committed_files(repo) == ["mine.py"]
    assert result.committed == ("mine.py",)
    assert result.foreign == ()
    assert len(result.foreign_staged_before) == 218, "før-målingen må se hva den lot være i fred"


def test_the_other_stream_s_staged_work_survives(repo, tmp_path):
    """Å ikke sveipe er halve jobben. Den andre halvparten er å ikke ødelegge."""
    (repo / "theirs.txt").write_text("theirs\n", encoding="utf-8")
    git(repo, "add", "theirs.txt")
    (repo / "mine.py").write_text("x = 1\n", encoding="utf-8")

    assert executor(repo, tmp_path).land(["mine.py"], "BL-4051: min").ok
    assert "theirs.txt" in git(repo, "diff", "--cached", "--name-only").splitlines()


def test_a_staged_version_of_my_own_file_does_not_win_over_the_worktree(repo, tmp_path):
    """Målt: `--only` lander ARBEIDSTREETS innhold, ikke det stagede.

    Verdt en egen test fordi den avgjør hva innholdskontrollen skal sammenligne
    mot — og fordi en parallell strøm som har staget en annen versjon av min fil
    ellers kunne fått sin versjon inn under mitt navn.
    """
    (repo / "mine.py").write_text("staget\n", encoding="utf-8")
    git(repo, "add", "mine.py")
    (repo / "mine.py").write_text("arbeidstre\n", encoding="utf-8")

    result = executor(repo, tmp_path).land(["mine.py"], "BL-4051: min")

    assert result.ok, result.reasons
    assert git(repo, "show", "HEAD:mine.py") == "arbeidstre"


# ------------------------------------------------- hva som ikke er en sti ---

def test_an_empty_landing_set_refuses_because_unknown_is_not_empty(repo, tmp_path):
    """Samme regel som vakten: fravær av data er ikke et positivt funn."""
    result = executor(repo, tmp_path).land([], "BL-4051")
    assert not result.ok
    assert any("empty or unknown" in r for r in result.reasons)
    assert result.commit == ""


def test_a_glob_refuses_because_git_would_expand_past_what_the_gate_judged(repo, tmp_path):
    (repo / "a.py").write_text("a\n", encoding="utf-8")
    (repo / "b.py").write_text("b\n", encoding="utf-8")
    result = executor(repo, tmp_path).land(["*.py"], "BL-4051")
    assert not result.ok
    assert any("glob" in r for r in result.reasons)
    assert committed_files(repo) == ["base.txt"], "ingenting skal ha landet"


def test_a_directory_refuses_because_git_expands_it_to_every_file_beneath(repo, tmp_path):
    """Målt: `git commit --only -- d` lander HVER fil under d.

    Vakten ville da ha dømt én oppføring mens N filer landet — nøyaktig hullet
    steg 11 finnes for å lukke, gjeninnført gjennom en «sti».
    """
    (repo / "d").mkdir()
    (repo / "d" / "a.py").write_text("a\n", encoding="utf-8")
    (repo / "d" / "b.py").write_text("b\n", encoding="utf-8")
    result = executor(repo, tmp_path).land(["d"], "BL-4051")
    assert not result.ok
    assert any("directory" in r for r in result.reasons)


def test_an_unnormalised_spelling_refuses_before_git_rewrites_it(repo, tmp_path):
    """`./mine.py` er lovlig for git, men git leser den tilbake som `mine.py`.

    Etterkontrollen sammenligner strenger. Slapp stavemåten gjennom, ville en
    HELT RIKTIG commit blitt meldt som både «fremmed fil kom med» og «deklarert
    fil landet ikke» — og siden commiten allerede er gjort, møter et nytt forsøk
    «nothing to commit». En falsk-positiv i den detektoren som skal ha siste ord.
    """
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    (repo / "d").mkdir()
    (repo / "d" / "a.py").write_text("a\n", encoding="utf-8")

    for spelling in ("./mine.py", "d//a.py", "d/"):
        result = executor(repo, tmp_path).land([spelling], "BL-4051")
        assert not result.ok, spelling
        assert committed_files(repo) == ["base.txt"], f"{spelling} committet noe"


def test_a_dot_path_refuses(repo, tmp_path):
    """`git add .` er den navngitte forbudte handlingen; `.` som sti er den samme."""
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    assert not executor(repo, tmp_path).land(["."], "BL-4051").ok


def test_absolute_and_escaping_paths_refuse(repo, tmp_path):
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    absolute = executor(repo, tmp_path).land([str(repo / "mine.py")], "BL-4051")
    assert not absolute.ok
    assert any("absolute" in r for r in absolute.reasons)

    escaping = executor(repo, tmp_path).land(["../outside.py"], "BL-4051")
    assert not escaping.ok
    assert any("climbs out" in r for r in escaping.reasons)


def test_a_path_that_is_neither_tracked_nor_present_refuses(repo, tmp_path):
    result = executor(repo, tmp_path).land(["finnes_ikke.py"], "BL-4051")
    assert not result.ok
    assert any("neither tracked nor present" in r for r in result.reasons)


def test_an_empty_message_refuses(repo, tmp_path):
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    result = executor(repo, tmp_path).land(["mine.py"], "   ")
    assert not result.ok
    assert any("message is empty" in r for r in result.reasons)


# ------------------------------------------------------- ekte landingsjobb ---

def test_a_new_file_lands_which_only_works_because_of_add_N(repo, tmp_path):
    """Uten `git add -N` ser `--only` ikke en fil git ikke kjenner."""
    (repo / "mine.py").write_text("x = 1\n", encoding="utf-8")
    assert git(repo, "ls-files", "--", "mine.py") == "", "forutsetningen: usporet"

    result = executor(repo, tmp_path).land(["mine.py"], "BL-4051: ny fil")

    assert result.ok, result.reasons
    assert committed_files(repo) == ["mine.py"]


def test_a_deletion_lands(repo, tmp_path):
    (repo / "gone.py").write_text("x\n", encoding="utf-8")
    git(repo, "add", "gone.py")
    git(repo, "commit", "-qm", "add gone")
    (repo / "gone.py").unlink()

    result = executor(repo, tmp_path).land(["gone.py"], "BL-4051: slett")

    assert result.ok, result.reasons
    assert committed_files(repo) == ["gone.py"]
    assert git(repo, "ls-tree", "--name-only", "HEAD", "gone.py") == "", "fila skal være borte i treet"


def test_nothing_to_commit_refuses_rather_than_reporting_success(repo, tmp_path):
    """Git nekter, og utføreren skal si det — ikke returnere en tom seier."""
    result = executor(repo, tmp_path).land(["base.txt"], "BL-4051: ingen endring")
    assert not result.ok
    assert any("refused the landing set" in r for r in result.reasons)


def test_a_multi_file_landing_lands_exactly_those_files(repo, tmp_path):
    for name in ("a.py", "b.py"):
        (repo / name).write_text("x\n", encoding="utf-8")
    (repo / "c_ikke_deklarert.py").write_text("x\n", encoding="utf-8")

    result = executor(repo, tmp_path).land(["a.py", "b.py"], "BL-4051: to filer")

    assert result.ok, result.reasons
    assert committed_files(repo) == ["a.py", "b.py"]


def test_a_non_ascii_filename_lands_and_verifies(repo, tmp_path):
    """Uten `-z` skriver git navnet om til "faber_l\\303\\245nding.py".

    Etterkontrollen ville da meldt både fremmed fil og manglende fil om en commit
    som var helt riktig. Repoet er norsk; dette er ikke et hjørnetilfelle.
    """
    (repo / "faber_lånding.py").write_text("x\n", encoding="utf-8")

    result = executor(repo, tmp_path).land(["faber_lånding.py"], "BL-4051: norsk filnavn")

    assert result.ok, result.reasons
    assert result.committed == ("faber_lånding.py",)
    assert result.foreign == () and result.missing == ()


# ------------------------------------------------------- etterkontrollen ----

def test_verification_names_a_foreign_file_that_came_along(repo, tmp_path):
    """Bevis at etterkontrollen faktisk måler commiten, ikke deklarasjonen.

    Her lages en commit med to filer med bar git, og utføreren blir bedt om å
    verifisere den mot et deklarert sett på én. Kommer den ut PASS, måler den
    ingenting.
    """
    ex = executor(repo, tmp_path)
    for name in ("mine.py", "andres.py"):
        (repo / name).write_text("x\n", encoding="utf-8")
    snapshot = ex._snapshot(["mine.py"])
    git(repo, "add", "mine.py", "andres.py")
    git(repo, "commit", "-qm", "to filer")

    result = ex._verify(["mine.py"], snapshot, git(repo, "rev-parse", "HEAD"), "to filer")

    assert not result.ok
    assert result.foreign == ("andres.py",)
    assert any("andres.py" in r for r in result.reasons), "den fremmede fila må NAVNGIS"
    assert any("2 file(s)" in r for r in result.reasons)


def test_a_foreign_file_named_like_a_section_marker_is_still_named(repo, tmp_path):
    """Et filnavn skal ikke kunne forkle seg som utførerens egen utdata-struktur.

    Markørbaserte seksjoner i én stdout gjorde nettopp det mulig: en fremmed fil
    som het `@@END@@` forsvant sporløst ut av rapporten. Fail-closed på antallet,
    men aldri NAVNGITT — og navngivningen er hele poenget med steg 11.
    """
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    (repo / "@@END@@").write_text("y\n", encoding="utf-8")
    snapshot = ex._snapshot(["mine.py"])
    git(repo, "add", "mine.py", "@@END@@")
    git(repo, "commit", "-qm", "markoer")

    result = ex._verify(["mine.py"], snapshot, git(repo, "rev-parse", "HEAD"), "markoer")

    assert not result.ok
    assert result.foreign == ("@@END@@",)
    assert any("@@END@@" in r for r in result.reasons)


def test_verification_catches_a_declared_file_that_did_not_land(repo, tmp_path):
    """Deklarasjonen var det vakten dømte; en fil som ikke landet gjør den usann."""
    ex = executor(repo, tmp_path)
    for name in ("a.py", "b.py"):
        (repo / name).write_text("x\n", encoding="utf-8")
    snapshot = ex._snapshot(["a.py", "b.py"])
    git(repo, "add", "a.py")
    git(repo, "commit", "-qm", "bare a")

    result = ex._verify(["a.py", "b.py"], snapshot, git(repo, "rev-parse", "HEAD"), "bare a")

    assert not result.ok
    assert result.missing == ("b.py",)
    assert any("did not land" in r for r in result.reasons)


def test_verification_catches_content_written_under_us(repo, tmp_path):
    """Riktig filsett er ikke nok: bytene må være de som ble målt og reviewet."""
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("reviewet\n", encoding="utf-8")
    snapshot = ex._snapshot(["mine.py"])
    (repo / "mine.py").write_text("skrevet av en annen stroem\n", encoding="utf-8")
    git(repo, "add", "mine.py")
    git(repo, "commit", "-qm", "annet innhold")

    result = ex._verify(["mine.py"], snapshot, git(repo, "rev-parse", "HEAD"), "annet innhold")

    assert not result.ok
    assert any("content changed" in r for r in result.reasons)


def test_the_readback_measures_OUR_commit_not_whatever_HEAD_became(repo, tmp_path):
    """Et tidligere utkast spurte om HEAD og ga ok=True på en annen strøms commit.

    Her committer en parallell strøm etter oss, så HEAD er ikke lenger vår. Vår
    SHA, våre filer — ellers navngir evidensen en commit denne landingen ikke
    lagde.
    """
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    snapshot = ex._snapshot(["mine.py"])
    ex._stage(["mine.py"], snapshot)
    ok, sha, _ = ex._commit(["mine.py"], "BL-4051: min")
    assert ok and sha

    (repo / "theirs.py").write_text("y\n", encoding="utf-8")
    git(repo, "add", "theirs.py")
    git(repo, "commit", "-qm", "en annen stroem kom etter")
    assert git(repo, "rev-parse", "HEAD") != sha, "forutsetningen: HEAD er ikke lenger vår"

    result = ex._verify(["mine.py"], snapshot, sha, "BL-4051: min")

    assert result.ok, result.reasons
    assert result.commit == sha
    assert result.committed == ("mine.py",)


def test_a_commit_that_is_not_ours_is_caught_by_its_subject(repo, tmp_path):
    """Belte og bukseseler: selv med feil SHA skal en forveksling ikke passere."""
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    snapshot = ex._snapshot(["mine.py"])
    git(repo, "add", "mine.py")
    git(repo, "commit", "-qm", "en helt annen commit")

    result = ex._verify(["mine.py"], snapshot, git(repo, "rev-parse", "HEAD"), "BL-4051: min")

    assert not result.ok
    assert any("is not the one this landing wrote" in r for r in result.reasons)


@pytest.mark.parametrize(
    "message",
    [
        "BL-4051: en tittel som\nbretter seg over to linjer",
        "BL-4051: tittel   \n\nbroedtekst under en blank linje",
        "A\nB\nC",
        "BL-4051:  dobbelt  mellomrom i tittelen",
    ],
    ids=["brettet-foerste-avsnitt", "etterfoelgende-blanktegn", "tre-linjer-uten-blank",
         "dobbelt-mellomrom"],
)
def test_ordinary_multiline_messages_are_not_mistaken_for_someone_elses_commit(repo, tmp_path, message):
    """`%s` er ikke «første linje», og forskjellen er ikke et hjørnetilfelle.

    Git bretter første avsnitt til én linje og fjerner etterfølgende blanktegn.
    Med `splitlines()[0]` ble en HELT RIKTIG commit meldt som «this is not the
    commit this landing wrote» — samme falsk-positiv-klasse som siterte filnavn
    og unormaliserte stavemåter, og like ubotelig: commiten er allerede gjort,
    så et nytt forsøk møter «nothing to commit».

    Sjekken ble lagt inn som ekstra sikring. En sikring som feller riktige
    landinger er ikke ekstra sikring.
    """
    (repo / "mine.py").write_text("x\n", encoding="utf-8")

    result = executor(repo, tmp_path).land(["mine.py"], message)

    assert result.ok, result.reasons
    assert result.committed == ("mine.py",)


def test_a_concurrent_commit_is_observed_but_does_not_condemn_our_own_scope(repo, tmp_path):
    """En annen strøm som committer FØR oss endrer ikke VÅRT filsett."""
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    snapshot = ex._snapshot(["mine.py"])
    (repo / "theirs.py").write_text("y\n", encoding="utf-8")
    git(repo, "add", "theirs.py")
    git(repo, "commit", "-qm", "en annen strøm rakk foran")
    ex._stage(["mine.py"], snapshot)
    _, sha, _ = ex._commit(["mine.py"], "BL-4051: min")

    result = ex._verify(["mine.py"], snapshot, sha, "BL-4051: min")

    assert result.ok, result.reasons
    assert any("another commit landed between" in o for o in result.observations)


def test_the_readback_is_written_down(repo, tmp_path):
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    executor(repo, tmp_path).land(["mine.py"], "BL-4051: notat")
    record = json.loads((tmp_path / "landings.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["ok"] is True
    assert record["committed"] == ["mine.py"] == record["declared"]


# ------------------------------- feil som skjer MENS vi rører delt tilstand --

def test_a_git_that_never_reports_back_still_names_the_commit_that_may_exist(repo, tmp_path):
    """Målt: en post-commit-hook som sover forbi tidsavbruddet gir en ekte commit.

    Lar man `TimeoutExpired` gå rett gjennom, mistes SHA-en til nettopp den
    foreldreløse commiten — og et nytt forsøk møter «nothing to commit» uten at
    noen vet hvorfor.
    """
    hook(repo, "post-commit", "sleep 5")
    (repo / "mine.py").write_text("x\n", encoding="utf-8")

    result = executor(repo, tmp_path, timeout=2).land(["mine.py"], "BL-4051: treg hook")

    assert not result.ok
    assert result.commit, "SHA-en til den mulige commiten må navngis"
    assert any("MAY exist" in r for r in result.reasons)
    assert committed_files(repo) == ["mine.py"], "commiten finnes faktisk"


def test_a_failed_commit_leaves_no_intent_to_add_in_the_shared_index(repo, tmp_path):
    """`A <fil>` i den DELTE indeksen ville blitt sveipet av en annen strøms
    `git commit -a`. Modulen ville brutt sitt eget prinsipp én etasje ned."""
    hook(repo, "pre-commit", "exit 1")
    (repo / "mine.py").write_text("x\n", encoding="utf-8")

    result = executor(repo, tmp_path).land(["mine.py"], "BL-4051: blir nektet")

    assert not result.ok
    assert git(repo, "status", "--porcelain", "--", "mine.py") == "?? mine.py", "ingen rest i indeksen"


def test_the_cleanup_never_discards_another_streams_staged_content(repo, tmp_path):
    """Opprydding må ikke bli en ny ødeleggelse.

    Målt: `git reset -- <sti>` kaster ekte staget innhold. Derfor ryddes kun
    stier som fortsatt står med den TOMME bloben, altså ren intent-to-add.
    """
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("ekte innhold fra en annen strøm\n", encoding="utf-8")
    git(repo, "add", "mine.py")
    staged_before = git(repo, "ls-files", "--stage", "--", "mine.py")

    ex._undo_our_intent_to_add(("mine.py",))

    assert git(repo, "ls-files", "--stage", "--", "mine.py") == staged_before


def test_the_cleanup_leaves_even_an_empty_file_another_stream_staged(repo, tmp_path):
    """Det siste hullet i tom-blob-heuristikken, lukket med en måling.

    En genuint TOM fil en annen strøm har staget har samme blob som vår egen
    intent-to-add. Målt skille: en ren intent-to-add vises IKKE i
    `git diff --cached --name-only`, mens en ekte staget fil gjør det. Uten det
    krysset ville oppryddingen kastet deres oppføring.
    """
    ex = executor(repo, tmp_path)
    (repo / "mine.py").write_text("", encoding="utf-8")
    git(repo, "add", "mine.py")
    assert "mine.py" in git(repo, "diff", "--cached", "--name-only"), "forutsetningen: ekte staget"
    staged_before = git(repo, "ls-files", "--stage", "--", "mine.py")

    ex._undo_our_intent_to_add(("mine.py",))

    assert git(repo, "ls-files", "--stage", "--", "mine.py") == staged_before


def test_a_locked_index_is_diagnosed_as_a_locked_index(repo, tmp_path):
    """Ellers får brukeren «pathspec did not match any files» — ærlig utfall,
    feil diagnose."""
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    try:
        result = executor(repo, tmp_path).land(["mine.py"], "BL-4051")
    finally:
        (repo / ".git" / "index.lock").unlink()

    assert not result.ok
    assert any("git add -N could not record" in r for r in result.reasons)


# ------------------------------------------- den håndhevede stien: runneren --

def _preflight(lease: str) -> PreflightResult:
    return PreflightResult(
        PreflightStatus.PASS,
        (),
        PreflightInput(
            git_clean=True, lease_clear=True, cad_status="fresh", adr_status="accepted",
            bl_status="open", obsidian_status="fresh",
            source_refs={"git": "g", "lease": lease, "cad": "C", "adr": "A", "bl": "B"},
        ),
    )


def _prelanding(landing_set: tuple[str, ...]) -> LandingEvidence:
    return LandingEvidence(
        commit="deklarert-sha", reviewer=ReviewVerdict.PASS, tests="ok", readback="ok",
        runtime_smoke="ok", rollback="ok", brain_change_log="ok", selfstate="ok",
        commit_closer="ok", landing_set=landing_set,
    )


def _run(repo: Path, tmp_path: Path, *, lease: str, landing_set: tuple[str, ...], message: str):
    prelanding = _prelanding(landing_set)
    return GovernedCodeRunner().run(
        FaberGoal("g1", "run", cad_ref="C", adr_ref="A", bl_ref="B"),
        preflight=_preflight(lease),
        build=lambda: {"tests": "ok", "diff_id": "d1", "changed_files": len(landing_set), "changed_lines": 10},
        review=lambda e: ReviewEvidence(verdict=ReviewVerdict.PASS, diff_id="d1", reviewer="symbiose-reviewer"),
        prelanding_evidence=prelanding,
        landing=landing_callable(
            message=message, prelanding=prelanding, executor=executor(repo, tmp_path),
        ),
    )


def test_the_hand_cannot_be_handed_a_set_the_gate_never_judged():
    """B1, målt av en review: med et eget `landing_set`-argument landet
    `('mine.py', 'IKKE_LEASET.py')` mens vakten dømte `('mine.py',)`, og målet
    gikk til LANDED.

    Invarianten var bare prosa i en docstring — samme feilklasse som hele
    modulen handler om. Nå er divergensen ikke representerbar.
    """
    assert "landing_set" not in inspect.signature(landing_callable).parameters


def test_the_runner_lands_through_the_executor_and_carries_the_MEASURED_commit(repo, tmp_path):
    """Hele kjeden: vakten godkjenner settet, hånden utfører det, evidensen måler.

    Den avgjørende assertionen er at ``commit`` IKKE lenger er den deklarerte
    strengen. Det var akkurat det stubben gjorde — gjentok en påstand.
    """
    (repo / "mine.py").write_text("x = 1\n", encoding="utf-8")
    result = _run(repo, tmp_path, lease="mine.py,annen.py", landing_set=("mine.py",), message="BL-4051: ekte landing")

    assert result.goal.state is GoalState.LANDED, result.blocker
    assert result.goal.evidence["commit"] == git(repo, "rev-parse", "HEAD")
    assert result.goal.evidence["commit"] != "deklarert-sha"
    assert committed_files(repo) == ["mine.py"]


def test_the_runner_BLOCKS_when_the_executor_cannot_land(repo, tmp_path):
    """Et avslag fra hånden må stoppe målet, ikke bli en stille no-op."""
    result = _run(repo, tmp_path, lease="finnes_ikke.py", landing_set=("finnes_ikke.py",), message="BL-4051")
    assert result.goal.state is GoalState.BLOCKED
    assert "LandingRefused" in result.blocker


def test_the_gate_still_stops_an_out_of_lease_set_before_the_hand_runs(repo, tmp_path):
    """Utføreren skal aldri få se et sett vakten ikke har godkjent."""
    (repo / "mine.py").write_text("x\n", encoding="utf-8")
    (repo / "ikke_leaset.py").write_text("y\n", encoding="utf-8")
    result = _run(repo, tmp_path, lease="mine.py", landing_set=("mine.py", "ikke_leaset.py"), message="BL-4051")

    assert result.goal.state is GoalState.BLOCKED
    assert "not a subset" in result.blocker
    assert committed_files(repo) == ["base.txt"], "hånden må ikke ha kjørt i det hele tatt"


# --------------------------------------------------- forbudte git-former ----

def _source() -> str:
    return Path(__import__("agent.faber_landing", fromlist=["x"]).__file__).read_text(encoding="utf-8")


def _code_only() -> str:
    """Kilden uten docstrings.

    Modulen BESKRIVER `git commit -a` og `git add .` i prosa, som de formene den
    finnes for å unngå. En tripwire som ikke skiller beskrivelsen fra kallet
    fyrer på sin egen dokumentasjon — og den enkleste måten å gjøre den grønn på
    ville vært å slutte å forklare hvorfor vernet finnes.

    Skall-konstantene (`_COMMIT_SCRIPT` m.fl.) er IKKE docstrings og blir stående:
    det er der den ekte commit-formen bor.

    Linjeområder, ikke tekst-erstatning: en docstring som inneholder escapes har
    en PARSET verdi som ikke finnes ordrett i kilden, og en `replace` på den
    verdien fjerner da ingenting — stille. Det var slik denne hjelperen først
    var skrevet, og den lot tripwiren fyre på prosaen den skulle hoppe over.
    """
    source = _source()
    lines = source.splitlines()
    skip: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            skip.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return "\n".join(line for number, line in enumerate(lines, 1) if number not in skip)


def test_the_executor_never_writes_the_forbidden_git_forms():
    """Regresjonsvakt på kilden selv, i både argv- og skallform.

    `git commit -a` og `git add .` er de to formene som forårsaket sveipet. De
    skal ikke kunne snike seg inn i en senere redigering uten at en test sier fra.
    """
    source = _code_only()
    assert not re.search(r'"commit",\s*"-a"', source) and not re.search(r"git\s+commit\s+-a\b", source)
    assert not re.search(r'"add",\s*"\."', source) and not re.search(r"git\s+add\s+\.(\s|$)", source)
    assert "--only" in source, "--only er selve vernet"
    assert "-N" in source, "-N er det som gjør nye filer landbare uten å stage bredt"


def test_the_executor_never_pushes():
    """Tre remotes, og `origin` er AGI — ikke hermes.

    En bar push herfra ville truffet feil repo. Modulen lander lokalt og lar en
    navngitt remote være et bevisst, separat valg. En subprocess-form ville hatt
    push som et sitert argument; prosaen i docstringen nevner det uten.
    """
    source = _source()
    assert '"push"' not in source and "'push'" not in source
    assert not re.search(r"git\s+push", source)
