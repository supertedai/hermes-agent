from __future__ import annotations

import json
import subprocess

import pytest

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
