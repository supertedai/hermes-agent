from __future__ import annotations

import json
import subprocess

import pytest

import agent.code_workflow as cw
from agent.code_workflow import RetiredFleetGate, RuntimeSmokeGate
from agent import faber_postcommit_adapters as ad


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real throwaway git repo — these adapters make claims about git."""
    r = tmp_path / "repo"
    r.mkdir()

    def git(*args, **kw):
        subprocess.run(["git", *args], cwd=str(r), check=True, capture_output=True, **kw)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "T")
    (r / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    git("add", "mod.py")
    git("commit", "-qm", "first: add mod")

    monkeypatch.setattr(ad, "REPO_ROOT", r)
    monkeypatch.setenv("HERMES_FABER_HOME", str(tmp_path / "faberhome"))
    # BL-4052: the import smoke actually spawns an interpreter now, and the
    # throwaway repo has no .venv. Point it at the one running the tests.
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    return r


def head(repo):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                          capture_output=True, text=True).stdout.strip()


def test_commit_closer_records_a_landed_commit(repo):
    sha = head(repo)

    evidence = ad.commit_closer(sha, repo=repo)

    assert sha[:12] in evidence
    line = (ad.faber_home() / "commit-closures.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["commit"] == sha
    assert record["reachable_from_head"] is True
    assert record["files"] == ["mod.py"]


def test_commit_closer_refuses_an_unknown_commit(repo):
    assert ad.commit_closer("0" * 40, repo=repo) == ""


def test_commit_closer_refuses_a_commit_not_reachable_from_head(repo):
    """Existing is not landing — the case a closure record must not bless."""
    subprocess.run(["git", "checkout", "-q", "-b", "side"], cwd=str(repo), check=True, capture_output=True)
    (repo / "orphan.py").write_text("X = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "orphan.py"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "side commit"], cwd=str(repo), check=True, capture_output=True)
    side = head(repo)
    subprocess.run(["git", "checkout", "-q", "-"], cwd=str(repo), check=True, capture_output=True)

    assert ad.commit_closer(side, repo=repo) == ""


def test_change_log_is_created_and_appended(repo):
    sha = head(repo)
    log = repo / "docs" / "FABER_CHANGE_LOG.md"

    evidence = ad.brain_change_log(sha, repo=repo, path=log)

    assert evidence
    text = log.read_text(encoding="utf-8")
    assert sha[:12] in text
    # It must not claim to be the vault it cannot reach.
    assert "IKKE" in text and "Obsidian" in text


def test_selfstate_is_explicitly_hermes_local(repo):
    sha = head(repo)

    assert ad.selfstate(sha, repo=repo)

    record = json.loads((ad.faber_home() / "selfstate.jsonl").read_text(encoding="utf-8").strip())
    assert record["scope"] == "hermes.local"
    assert record["commit"] == sha


def test_readback_fails_until_all_three_artifacts_exist(repo):
    sha = head(repo)
    log = repo / "docs" / "FABER_CHANGE_LOG.md"

    assert ad.readback(sha) == ""
    ad.commit_closer(sha, repo=repo)
    assert ad.readback(sha) == ""
    ad.selfstate(sha, repo=repo)
    assert ad.readback(sha) == ""

    ad.brain_change_log(sha, repo=repo, path=log)
    # readback() resolves the change log against REPO_ROOT, which the fixture
    # has pointed at this repo.
    assert "change_log" in ad.readback(sha)


def test_rollback_verifies_reversibility_without_touching_the_worktree(repo):
    sha = head(repo)
    before = (repo / "mod.py").read_text(encoding="utf-8")

    evidence = ad.rollback(sha, repo=repo)

    assert "applies cleanly" in evidence
    assert (repo / "mod.py").read_text(encoding="utf-8") == before


def test_rollback_refuses_an_unknown_commit(repo):
    assert ad.rollback("0" * 40, repo=repo) == ""


def test_learning_event_derives_its_verdict_from_the_numbers(tmp_path):
    log = tmp_path / "learning.jsonl"

    up = ad.record_learning(commit="abc", goal_id="g", metric="m", baseline=1, after=2,
                            method="counted", confidence=0.9, log=log)
    down = ad.record_learning(commit="abc", goal_id="g", metric="m", baseline=2, after=1,
                              method="counted", confidence=0.9, log=log)
    flat = ad.record_learning(commit="abc", goal_id="g", metric="m", baseline=2, after=2,
                              method="counted", confidence=0.9, log=log)

    assert up.status == "confirmed" and up.to_dict()["delta"] == 1
    assert down.status == "refuted"
    # The easiest place to assert learning that did not happen.
    assert flat.status == "inconclusive"
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 3


def test_learning_event_rejects_an_incomplete_or_impossible_claim(tmp_path):
    log = tmp_path / "learning.jsonl"
    common = dict(commit="abc", goal_id="g", metric="m", baseline=1, after=2, log=log)

    assert ad.record_learning(**{**common, "method": "", "confidence": 0.9}) is None
    assert ad.record_learning(**{**common, "method": "counted", "confidence": 1.5}) is None
    assert ad.record_learning(**{**common, "method": "counted", "confidence": -0.1}) is None
    assert not log.exists()


# ===========================================================================
# BL-4052 — steg 12 og steg 13, adaptere
# ===========================================================================

import os  # noqa: E402
import stat as _stat  # noqa: E402
import sys  # noqa: E402

from agent.code_workflow import PostcommitReadbackGate, StepBlocked  # noqa: E402


def commit_file(repo, name, text, message):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=str(repo), check=True, capture_output=True)
    return head(repo)


# --- steg 13: les commiten tilbake ----------------------------------------

def test_commit_readback_reports_the_exact_file_set(repo):
    sha = commit_file(repo, "docs/note.md", "hi\n", "BL-4052 add note")

    rb = ad.commit_readback(sha, repo=repo)

    assert rb.resolved and rb.reachable_from_head is True
    assert rb.files == ("docs/note.md",)
    assert "BL-4052" in rb.subject


def test_commit_readback_reports_a_root_commit_rather_than_nothing(repo):
    """--root: ellers ser den foerste commiten ut som om den ikke roerte noe."""
    first = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=str(repo),
                           capture_output=True, text=True).stdout.strip()

    assert ad.commit_readback(first, repo=repo).files == ("mod.py",)


def test_commit_readback_does_not_claim_a_commit_it_could_not_find(repo):
    rb = ad.commit_readback("0" * 40, repo=repo)

    assert rb.resolved is False
    assert rb.files is None      # ukjent, ikke tomt


def test_postcommit_readback_blocks_on_a_foreign_file(repo):
    """Sveipet: commiten baerer en fil den aldri skulle roert."""
    (repo / "wanted.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "stowaway.py").write_text("B = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "BL-4052 land wanted"], cwd=str(repo),
                   check=True, capture_output=True)
    sha = head(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.postcommit_readback(sha, expected_files=("wanted.py",), repo=repo)

    assert "stowaway.py" in str(caught.value)
    assert "never meant to touch" in str(caught.value)


def test_postcommit_readback_blocks_when_the_commit_does_not_exist(repo):
    with pytest.raises(StepBlocked) as caught:
        ad.postcommit_readback("0" * 40, expected_files=("mod.py",), repo=repo)

    assert "could not be read back" in str(caught.value)


def test_postcommit_readback_passes_on_an_exact_landing(repo):
    sha = commit_file(repo, "wanted.py", "A = 1\n", "BL-4052 land wanted")
    ad.commit_closer(sha, repo=repo)
    ad.selfstate(sha, repo=repo)
    ad.brain_change_log(sha, repo=repo, path=repo / "docs" / "FABER_CHANGE_LOG.md")

    evidence = ad.postcommit_readback(sha, expected_files=("wanted.py",),
                                      require_ref="BL-4052", repo=repo)

    assert "no foreign files" in evidence


def test_postcommit_readback_blocks_when_faber_recorded_nothing(repo):
    """Git stemmer, men ingen lokal spor av landingen finnes."""
    sha = commit_file(repo, "wanted.py", "A = 1\n", "BL-4052 land wanted")

    with pytest.raises(StepBlocked) as caught:
        ad.postcommit_readback(sha, expected_files=("wanted.py",), repo=repo)

    assert "nobody recorded" in str(caught.value)


# --- steg 12: import-roeyk -------------------------------------------------

def test_import_smoke_distinguishes_a_measured_empty_set_from_an_unknown_one(repo):
    """Hullet i den arvede adapteren: 'not applicable' var ikke-tom => bestaatt."""
    sha = commit_file(repo, "docs/note.md", "hi\n", "docs only")

    evidence = ad._import_smoke(sha, repo=repo)

    assert "1 file(s) changed, none of them importable modules" in evidence
    assert "measured, not assumed" in evidence


def test_import_smoke_blocks_on_a_commit_that_touches_nothing(repo):
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "empty"],
                   cwd=str(repo), check=True, capture_output=True)

    with pytest.raises(StepBlocked) as caught:
        ad._import_smoke(head(repo), repo=repo)

    assert "touches no files" in str(caught.value)


def test_import_smoke_blocks_when_git_cannot_read_the_commit(repo):
    with pytest.raises(StepBlocked) as caught:
        ad._import_smoke("0" * 40, repo=repo)

    assert "not a smoke-tested commit" in str(caught.value)


# --- steg 12: docker-proben ------------------------------------------------

INSPECT_JSON = {
    "State": {"Running": True, "StartedAt": "2026-08-10T19:07:07.602127692Z"},
    "Config": {"WorkingDir": "/repo", "Cmd": ["python", "-u", "-m", "tools.graph_healer"]},
    "Mounts": [
        {"Type": "bind", "Source": "/host/AGI", "Destination": "/repo"},
        {"Type": "bind", "Source": "/host/AGI/tools/graph_healer.py",
         "Destination": "/app/tools/graph_healer.py"},
        {"Type": "volume", "Source": "vol", "Destination": "/data"},
    ],
}


@pytest.fixture
def fake_docker(tmp_path):
    """En docker-stubb. Svarer paa inspect/exec/ps, og logger hva den ble spurt om."""
    log = tmp_path / "docker.log"
    script = tmp_path / "fakedocker"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, pathlib\n"
        f"LOG = pathlib.Path({str(log)!r})\n"
        f"INSPECT = {json.dumps(INSPECT_JSON)!r}\n"
        f"STATE = pathlib.Path({str(tmp_path / 'state.json')!r})\n"
        "args = sys.argv[1:]\n"
        "with LOG.open('a') as h: h.write(' '.join(args) + '\\n')\n"
        "cfg = json.loads(STATE.read_text()) if STATE.exists() else {}\n"
        "if args[0] == 'inspect':\n"
        "    if cfg.get('inspect_fails'): sys.exit(1)\n"
        "    print(json.dumps(json.loads(INSPECT)))\n"
        "elif args[0] == 'exec' and 'sha256sum' in args:\n"
        "    print(cfg.get('digest', 'abc123') + '  ' + args[-1])\n"
        "elif args[0] == 'exec' and 'stat' in args:\n"
        "    print(cfg.get('mtime', '1786385855'))\n"
        "elif args[0] == 'ps':\n"
        "    sys.stderr.write(cfg.get('ps_stderr', ''))\n"
        "    sys.stdout.write(cfg.get('ps', ''))\n"
        "else:\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | _stat.S_IEXEC)

    def configure(**cfg):
        (tmp_path / "state.json").write_text(json.dumps(cfg), encoding="utf-8")

    return script, configure, log


def test_docker_probe_measures_the_syspath_copy_and_uses_exec_not_cp(fake_docker):
    script, configure, log = fake_docker
    configure(digest="abc123", mtime="1786385855")     # 2026-08-10T18:17:35Z, foer StartedAt 19:07:07Z

    probe = ad.docker_runtime_probe(
        container="efc-tool", host_path="/host/AGI/tools/graph_healer.py",
        expected_digest="abc123", docker_cmd=[str(script)])

    assert probe.answered and probe.running is True
    # /repo-kopien, ikke den image-bakede /app-kopien
    assert probe.loaded_path == "/repo/tools/graph_healer.py"
    assert probe.observed_digest == "abc123"
    assert probe.probe_method == "docker exec"
    calls = log.read_text(encoding="utf-8")
    assert "exec efc-tool sha256sum /repo/tools/graph_healer.py" in calls
    assert " cp " not in calls and not calls.startswith("cp ")

    assert RuntimeSmokeGate().evaluate(probe).status is cw.PreflightStatus.PASS


def test_docker_probe_that_gets_no_answer_is_marked_unanswered(fake_docker):
    script, configure, _ = fake_docker
    configure(inspect_fails=True)

    probe = ad.docker_runtime_probe(container="efc-tool", host_path="/host/AGI/tools/x.py",
                                    expected_digest="abc123", docker_cmd=[str(script)])

    assert probe.answered is False
    assert RuntimeSmokeGate().evaluate(probe).status is cw.PreflightStatus.BLOCK


def landed_module(repo):
    """Legg en modul i commiten paa den stien fake-containeren binder inn."""
    return commit_file(repo, "tools/graph_healer.py", "VERSION = 'v1'\n",
                       "BL-4052 land graph_healer")


def test_runtime_smoke_step_blocks_when_the_process_predates_the_file(repo, fake_docker):
    """Fila er nyere enn prosessen: deployet, men ikke restartet."""
    script, configure, _ = fake_docker
    sha = landed_module(repo)
    configure(digest=ad.digest_of_commit_blob(sha, "tools/graph_healer.py", repo=repo),
              mtime="1786600000")   # godt etter StartedAt

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/host/AGI/tools/graph_healer.py",
                              repo_relpath="tools/graph_healer.py",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "source is NEWER than the running process" in str(caught.value)


def test_runtime_smoke_step_passes_when_the_process_runs_the_landed_content(repo, fake_docker):
    script, configure, _ = fake_docker
    sha = landed_module(repo)
    configure(digest=ad.digest_of_commit_blob(sha, "tools/graph_healer.py", repo=repo),
              mtime="1786385855")

    evidence = ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                                     host_path="/host/AGI/tools/graph_healer.py",
                                     repo_relpath="tools/graph_healer.py",
                                     docker_cmd=[str(script)], check_local_fleet=False)

    assert "reads the landed content" in evidence
    assert "written before that start" in evidence


def test_runtime_smoke_step_catches_a_process_serving_content_that_was_never_landed(repo, fake_docker):
    """Reviewer B2: fasiten maa komme fra COMMITEN, ikke fra en ny lesing av vertsfila.

    Scenarioet er ikke eksotisk i dette repoet: v1 landes, en parallell skriver
    overskriver arbeidstreet til v2, containeren restarter og kjoerer v2. Saa
    lenge «forventet» ble utledet ved aa lese vertsfila paa nytt, var observert
    og forventet den samme inoden gjennom bind-mounten -- sammenligningen kunne
    ikke feile, og steg 12 meldte «process verified» om innhold commiten aldri
    inneholdt.
    """
    script, configure, _ = fake_docker
    sha = landed_module(repo)
    # containeren serverer noe annet enn det commiten inneholder
    configure(digest="deadbeef" * 8, mtime="1786385855")

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/host/AGI/tools/graph_healer.py",
                              repo_relpath="tools/graph_healer.py",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "different file than the one landed" in str(caught.value)


def test_runtime_smoke_step_refuses_to_skip_the_process_check_by_default(repo):
    """Reviewer B1: dette var hullet, og en test pinnet det som oensket oppfoersel.

    Med `container` som tom default returnerte steget en ikke-tom streng som sa
    at prosessen IKKE var sjekket -- og `DefinitionOfDone` leser ikke prosa, den
    leser «ikke-tom» som «oppfylt». Standardveien gjennom steg 12 tilfredsstilte
    altsaa steg 12 uten aa maale en eneste prosess: dagens regel brutt inne i
    vakten som skulle haandheve den.
    """
    sha = landed_module(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, check_local_fleet=False)

    assert "no reason was declared" in str(caught.value)
    assert "read downstream as if it had been measured" in str(caught.value)


def test_runtime_smoke_step_accepts_an_explicitly_declared_absence_of_a_target(repo):
    """Uttrykt og loggfoert er greit; default er ikke."""
    sha = commit_file(repo, "docs/note.md", "hi\n", "docs only")

    evidence = ad.runtime_smoke_step(sha, repo=repo, check_local_fleet=False,
                                     no_runtime_target="documentation-only landing, no process serves it")

    assert "declared reason: documentation-only landing" in evidence


def test_runtime_smoke_step_refuses_a_target_without_the_committed_path(repo, fake_docker):
    script, _configure, _ = fake_docker
    sha = landed_module(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/host/AGI/tools/graph_healer.py",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "expected digest must come from the commit" in str(caught.value)


def test_runtime_smoke_step_blocks_on_a_non_empty_local_fleet(repo, monkeypatch, fake_docker):
    """ADR-043: avviket er i seg selv et varsel."""
    script, configure, _ = fake_docker
    configure(ps="efc-unified-api\nefc-mcp-mobile\n")
    monkeypatch.setenv("HERMES_LOCAL_DOCKER_CMD", str(script))
    sha = landed_module(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, check_local_fleet=True)

    assert "ADR-043" in str(caught.value)


def test_adr043_check_asks_this_host_even_when_runtime_probes_are_remote(monkeypatch, fake_docker):
    """Reviewer B9: HERMES_DOCKER_CMD er nettopp den man setter til `ssh byopus12 docker`.

    Brukte ADR-043-sjekken den, spurte «er den LOKALE flaaten tom?» en fjern vert
    med 283 containere, og hver eneste landing blokkerte.
    """
    script, configure, _ = fake_docker
    configure(ps="efc-unified-api\n")
    monkeypatch.setenv("HERMES_DOCKER_CMD", str(script))          # fjern-runtime
    monkeypatch.setenv("HERMES_LOCAL_DOCKER_CMD", "no-such-docker-binary")

    probed, names, note = ad.local_fleet_state()

    assert probed is True and names == ()
    assert "not installed" in note


# --- reviewer B4/B5/B6: filsett-lesing -------------------------------------

def test_readback_reports_a_merge_as_unknown_not_as_empty(repo):
    """Reviewer B4: diff-tree gir tomt filsett paa en merge, og tomt betyr her
    «roerer ingen filer» -- en faktisk usann begrunnelse."""
    subprocess.run(["git", "checkout", "-q", "-b", "side"], cwd=str(repo), check=True, capture_output=True)
    commit_file(repo, "side.py", "S = 1\n", "side work")
    subprocess.run(["git", "checkout", "-q", "-"], cwd=str(repo), check=True, capture_output=True)
    commit_file(repo, "main_side.py", "M = 1\n", "main work")
    subprocess.run(["git", "merge", "-q", "--no-ff", "side", "-m", "BL-4052 merge"],
                   cwd=str(repo), check=True, capture_output=True)

    rb = ad.commit_readback(head(repo), repo=repo)

    assert rb.resolved is True
    assert rb.files is None                      # ukjent, ikke tomt
    result = PostcommitReadbackGate().evaluate(rb, expected_files=("side.py",))
    assert result.status is cw.PreflightStatus.BLOCK
    assert "unknown" in " | ".join(result.reasons)
    assert "touches no files" not in " | ".join(result.reasons)


def test_readback_does_not_octal_quote_a_non_ascii_path(repo):
    """Reviewer B5: core.quotepath gjorde EN norsk fil til BAADE blindpassasjer og savnet."""
    sha = commit_file(repo, "h\u00e5ndbok.md", "hei\n", "BL-4052 add handbook")

    rb = ad.commit_readback(sha, repo=repo)

    assert rb.files == ("h\u00e5ndbok.md",)
    assert PostcommitReadbackGate().evaluate(
        rb, expected_files=("h\u00e5ndbok.md",)).status is cw.PreflightStatus.PASS


def test_import_smoke_does_not_try_to_import_a_deleted_module(repo, monkeypatch):
    """Reviewer B6: ellers kan ingen landing som FJERNER en modul noensinne passere."""
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    commit_file(repo, "gone.py", "G = 1\n", "add gone")
    subprocess.run(["git", "rm", "-q", "gone.py"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "remove gone"], cwd=str(repo), check=True, capture_output=True)

    evidence = ad._import_smoke(head(repo), repo=repo)

    assert "none of them importable modules" in evidence


def test_import_smoke_imports_real_modules_and_skips_the_test_tree(repo, monkeypatch):
    """Reviewer B8: ingen test naadde faktisk import-veien, saa den var uovervaaket."""
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "real_mod.py").write_text("OK = 1\n", encoding="utf-8")
    (repo / "tests" / "test_real.py").write_text("import nonexistent_xyz\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add module and test"], cwd=str(repo),
                   check=True, capture_output=True)

    # tests/ utelates -- ellers ville den umulige importen der felt hele steget
    assert ad._import_smoke(head(repo), repo=repo) == "import smoke: 1 module(s) imported"


def test_import_smoke_blocks_when_a_landed_module_cannot_be_imported(repo, monkeypatch):
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    commit_file(repo, "broken.py", "import definitely_not_a_module_xyz\n", "add broken")

    with pytest.raises(StepBlocked) as caught:
        ad._import_smoke(head(repo), repo=repo)

    assert "import failed" in str(caught.value)


def test_local_fleet_state_treats_a_missing_docker_as_a_measured_empty_fleet(tmp_path):
    """Ingen docker => ingen containere. Det er et funn, ikke en mislykket maaling."""
    probed, names, note = ad.local_fleet_state(docker_cmd=[str(tmp_path / "no-such-docker")])

    assert probed is True and names == ()
    assert "not installed" in note


def test_local_fleet_state_does_not_read_a_docker_warning_as_a_container(fake_docker, monkeypatch):
    """Reviewer B9: `stdout or stderr` gjorde en advarsel til et containernavn.

    En vellykket `docker ps` med tom stdout og en advarsel paa stderr ville da
    rapportere advarselsteksten som en kjoerende container -- og ADR-043-gaten
    ville blokkere hver eneste landing paa en flaate som faktisk er tom.
    """
    script, configure, _ = fake_docker
    configure(ps="", ps_stderr="WARNING: daemon is using an unsupported storage driver\n")
    monkeypatch.setenv("HERMES_LOCAL_DOCKER_CMD", str(script))

    probed, names, note = ad.local_fleet_state()

    assert probed is True
    assert names == ()
    assert RetiredFleetGate().evaluate(
        probed=probed, container_names=names).status is cw.PreflightStatus.PASS


def test_local_fleet_state_treats_a_failing_docker_as_unprobed(fake_docker):
    script, _configure, _ = fake_docker

    probed, names, note = ad.local_fleet_state(docker_cmd=[str(script), "bogus"])

    assert probed is False and names == ()
    assert RetiredFleetGate().evaluate(probed=probed, container_names=names).status \
        is cw.PreflightStatus.BLOCK


# --- reviewer runde 2 -------------------------------------------------------

def test_runtime_smoke_step_refuses_a_target_and_a_no_target_declaration_at_once(repo, fake_docker):
    """R1: den andre halvdelen av B1-fiksen var uovervaaket."""
    script, _configure, _ = fake_docker
    sha = landed_module(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/host/AGI/tools/graph_healer.py",
                              repo_relpath="tools/graph_healer.py",
                              no_runtime_target="also claiming there is no target",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "exactly one of them can be true" in str(caught.value)


def test_runtime_smoke_step_blocks_when_the_path_is_not_in_the_commit(repo, fake_docker):
    """R2: B2-fiksens EGEN feilvei -- fasiten kunne ikke leses."""
    script, _configure, _ = fake_docker
    sha = landed_module(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/host/AGI/tools/graph_healer.py",
                              repo_relpath="tools/never_committed.py",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "could not read tools/never_committed.py out of commit" in str(caught.value)


def test_digest_of_commit_blob_returns_empty_rather_than_hashing_nothing(repo):
    """R3: uten returkode-sjekken hashes tom stdout til e3b0c442..., som SER ut som en digest.

    Da ville R2-sjekken («fikk vi fasiten?») aldri kunne fyre, og steg 12 ville
    sammenligne containeren mot hashen av ingenting.
    """
    sha = landed_module(repo)
    empty_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    for missing in ("tools/never_committed.py", "tools", ""):
        assert ad.digest_of_commit_blob(sha, missing, repo=repo) == ""
    assert ad.digest_of_commit_blob("0" * 40, "tools/graph_healer.py", repo=repo) == ""
    assert ad.digest_of_commit_blob(sha, "tools/graph_healer.py", repo=repo) != empty_sha256


def test_runtime_smoke_step_surfaces_the_probe_note_in_the_block_reason(repo, fake_docker):
    """R6: fleet-tvillingen var testet, probe-siden ikke."""
    script, configure, _ = fake_docker
    sha = landed_module(repo)
    configure(digest="abc123", mtime="1786385855")

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/somewhere/else/graph_healer.py",   # ikke montert
                              repo_relpath="tools/graph_healer.py",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "is not visible inside" in str(caught.value)


def test_runtime_smoke_step_records_that_the_fleet_check_was_skipped(repo):
    """D1: en hoppet-over vakt maa SES i evidensen, ellers er den B1 om igjen."""
    sha = commit_file(repo, "docs/note.md", "hi\n", "docs only")

    skipped = ad.runtime_smoke_step(sha, repo=repo, check_local_fleet=False,
                                    no_runtime_target="docs only")

    assert "ADR-043 local-fleet check skipped by caller" in skipped


def test_runtime_smoke_step_treats_a_blank_container_as_absent(repo):
    """D5: container ble ikke strippet, saa "   " klarerte B1-gaten."""
    sha = landed_module(repo)

    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="   ", check_local_fleet=False)

    assert "no reason was declared" in str(caught.value)


def test_import_smoke_measures_paths_that_cannot_be_module_names(repo, monkeypatch):
    """D2: 136 sporede .py-stier i dette repoet er ikke gyldige modulnavn.

    Foer fiksen blokkerte enhver commit som roerte én av dem steg 12 UBETINGET,
    og den forutsigbare snarveien var aa sende no_runtime_target -- altsaa aa
    gjoere den tomme veien til en vane.
    """
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    sha = commit_file(repo, "plugins/my-plugin/thing.py", "X = 1\n", "add plugin")

    evidence = ad._import_smoke(sha, repo=repo)

    assert "not importable module names" in evidence
    assert "plugins/my-plugin/thing.py" in evidence


def test_import_smoke_names_the_merge_as_the_reason(repo):
    """D3: 'merge commit, ELLER unreadable' naar informasjonen fantes."""
    subprocess.run(["git", "checkout", "-q", "-b", "side2"], cwd=str(repo), check=True, capture_output=True)
    commit_file(repo, "s2.py", "S = 1\n", "side work")
    subprocess.run(["git", "checkout", "-q", "-"], cwd=str(repo), check=True, capture_output=True)
    commit_file(repo, "m2.py", "M = 1\n", "main work")
    subprocess.run(["git", "merge", "-q", "--no-ff", "side2", "-m", "merge"],
                   cwd=str(repo), check=True, capture_output=True)

    with pytest.raises(StepBlocked) as caught:
        ad._import_smoke(head(repo), repo=repo)

    assert "it is a merge commit" in str(caught.value)
    assert ad.is_merge_commit(head(repo), repo=repo) is True


def test_runtime_smoke_step_refuses_a_symlinked_path_instead_of_reporting_a_mismatch(repo, fake_docker):
    """B2-forbehold: commiten lagrer lenkemaalet, containeren leser innholdet.

    De to kan aldri stemme, saa uten denne vakten ville steg 12 rapportert en
    innholdsforskjell som ikke finnes.
    """
    script, configure, _ = fake_docker
    (repo / "tools").mkdir(exist_ok=True)
    (repo / "tools" / "real.py").write_text("R = 1\n", encoding="utf-8")
    os.symlink("real.py", repo / "tools" / "link.py")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add symlink"], cwd=str(repo), check=True, capture_output=True)
    sha = head(repo)
    configure(digest="abc123", mtime="1786385855")

    assert ad.commit_entry_mode(sha, "tools/link.py", repo=repo) == "120000"
    with pytest.raises(StepBlocked) as caught:
        ad.runtime_smoke_step(sha, repo=repo, container="efc-tool",
                              host_path="/host/AGI/tools/link.py",
                              repo_relpath="tools/link.py",
                              docker_cmd=[str(script)], check_local_fleet=False)

    assert "is a symlink" in str(caught.value)
    assert "false mismatch" in str(caught.value)


def test_digest_falls_back_to_raw_blob_when_filters_are_unsupported(repo, monkeypatch):
    """R3b: uten returkode-sjekken ville det FOERSTE forsoeket returnere hashen
    av tom stdout, og fallbacken aldri bli naadd.

    Den veien er ikke naabar via ekte git her (mode-vakten fanger de tilfellene
    der cat-file feiler), saa den maa injiseres for i det hele tatt aa vaere
    overvaaket -- ellers er den kode uten test bak en vakt som ser dekket ut.
    """
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if "--filters" in cmd:
            return subprocess.CompletedProcess(cmd, 1, b"", b"unknown option --filters")
        return real_run(cmd, *args, **kwargs)

    sha = landed_module(repo)
    expected = ad.digest_of_commit_blob(sha, "tools/graph_healer.py", repo=repo)
    monkeypatch.setattr(ad.subprocess, "run", fake_run)

    got = ad.digest_of_commit_blob(sha, "tools/graph_healer.py", repo=repo)

    empty_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert got == expected and got != empty_sha256


def test_commit_entry_mode_requires_an_exact_path_not_a_pathspec(repo):
    """ls-tree tar en PATHSPEC, cat-file en LITERAL sti — de kan peke ulikt.

    Maalt: `git ls-tree <sha> -- "tools/"` lister BARNA, saa den foerste moden er
    100644. Vakten leste dermed modusen til en ANNEN oppfoering enn den som ville
    blitt hashet, og en katalogsti kunne passere en sjekk som skulle avvist den.
    """
    sha = landed_module(repo)

    assert ad.commit_entry_mode(sha, "tools/graph_healer.py", repo=repo) == "100644"

    # En katalog navngitt NOEYAKTIG gir sin egen tree-modus -- riktig svar, og
    # det er mode-vakten i digest_of_commit_blob som avviser den.
    assert ad.commit_entry_mode(sha, "tools", repo=repo) == "040000"

    # Alt som ikke er én entydig oppfoering med akkurat dette navnet gir "".
    # "tools/" er sakens kjerne: ls-tree lister da BARNA (foerste mode 100644).
    for not_one_named_entry in ("tools/", "tools/*.py", "*.py", "nope.py"):
        assert ad.commit_entry_mode(sha, not_one_named_entry, repo=repo) == "", not_one_named_entry

    for not_a_file in ("tools/", "tools", "tools/*.py", "*.py", "nope.py"):
        assert ad.digest_of_commit_blob(sha, not_a_file, repo=repo) == "", not_a_file


def test_declaring_no_runtime_target_while_landing_modules_is_marked_as_asserted(repo):
    """Reviewer Q2: erklaeringen kan ikke verifiseres herfra, men den skal ses."""
    sha = landed_module(repo)

    evidence = ad.runtime_smoke_step(sha, repo=repo, check_local_fleet=False,
                                     no_runtime_target="nothing serves this")

    assert "asserted, not measured" in evidence

    docs = commit_file(repo, "docs/n2.md", "hi\n", "docs only")
    assert "asserted, not measured" not in ad.runtime_smoke_step(
        docs, repo=repo, check_local_fleet=False, no_runtime_target="docs only")


def test_fleet_skip_is_recorded_on_the_measured_process_path_too(repo, fake_docker):
    """N6: D1-fiksen var halvt overvaaket — bare den ERKLAERTE veien var testet.

    Den umaalte halvdelen var HOVED-evidensstrengen for steg 12, altsaa nettopp
    den en leser stoler paa naar prosessen faktisk ble maalt.
    """
    script, configure, _ = fake_docker
    sha = landed_module(repo)
    configure(digest=ad.digest_of_commit_blob(sha, "tools/graph_healer.py", repo=repo),
              mtime="1786385855")

    common = dict(repo=repo, container="efc-tool",
                  host_path="/host/AGI/tools/graph_healer.py",
                  repo_relpath="tools/graph_healer.py", docker_cmd=[str(script)])

    skipped = ad.runtime_smoke_step(sha, check_local_fleet=False, **common)
    assert "reads the landed content" in skipped
    assert "ADR-043 local-fleet check skipped by caller" in skipped

    # ...og naar den FAKTISK kjoerte skal stempelet ikke staa der og lyve
    checked = ad.runtime_smoke_step(sha, check_local_fleet=True, **common)
    assert "reads the landed content" in checked
    assert "skipped by caller" not in checked


def test_q2_flag_reads_the_module_count_not_a_rendered_sentence(repo, monkeypatch):
    """Reviewer: flagget utledet en konklusjon av prosa. Nå leser det data.

    Bevises ved at flagget foelger `landed_modules`, ikke ordlyden: en modul med
    ugyldig modulnavn gir ingen importerbare moduler, saa erklaeringen skal IKKE
    stemples — selv om evidensstrengen nevner .py-filer.
    """
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    assert ad.landed_modules(landed_module(repo), repo=repo)[0] == ["tools.graph_healer"]

    odd = commit_file(repo, "plugins/my-plugin/x.py", "X = 1\n", "plugin only")
    mods, not_mods = ad.landed_modules(odd, repo=repo)
    assert mods == [] and not_mods == ["plugins/my-plugin/x.py"]

    evidence = ad.runtime_smoke_step(odd, repo=repo, check_local_fleet=False,
                                     no_runtime_target="nothing serves a plugin file")
    assert ".py path(s) are not importable module names" in evidence
    assert "asserted, not measured" not in evidence


def test_q2_flag_survives_a_rewording_of_the_import_smoke_sentence(repo, monkeypatch):
    """Invarianten reviewer ba om: flagget skal ikke avhenge av ORDLYDEN.

    Prosa-varianten (`if "module(s) imported" in imported`) og data-varianten
    oppfoerer seg likt paa all ekte input — den er en ekvivalent mutant helt til
    noen omformulerer setningen. DA slutter flagget stilltiende aa fyre, og en
    landing med importerbare moduler kan hevde «ingen prosess betjener dette»
    uten stempel. Denne testen gjoer den latente koblingen observerbar ved aa
    omformulere setningen med vilje.
    """
    monkeypatch.setenv("HERMES_PYTHON", sys.executable)
    sha = landed_module(repo)
    real = ad._import_smoke

    def reworded(s_, **kw):
        real(s_, **kw)                       # kjoer den ekte sjekken
        return "import check: 1 modul lastet uten feil"   # ...men si det annerledes

    monkeypatch.setattr(ad, "_import_smoke", reworded)

    evidence = ad.runtime_smoke_step(sha, repo=repo, check_local_fleet=False,
                                     no_runtime_target="nothing serves this")

    assert "asserted, not measured" in evidence
