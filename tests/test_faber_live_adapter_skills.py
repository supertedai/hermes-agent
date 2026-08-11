"""Beviser at seleksjonen faktisk NÅR workflowen (BL-4057).

Punkt 3 i oppgaven: «en seleksjon ingen kan observere er ikke koblet.» Å måle at
selektoren returnerer riktig skill beviser bare at selektoren virker — ikke at
kjeden bruker den. Disse testene fanger systemprompten som FAKTISK sendes til
modellen, og slår fast at den navngir den valgte skillen.

Det er forskjellen på den gamle koblingen og den nye: den gamle var en setning om
at modellen har skills, og den kunne ikke feile en test fordi den ikke gjorde noe.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent.faber_live_adapter as adapter  # noqa: E402
import agent.skill_selector as selector  # noqa: E402


class _Envelope:
    goal_id = "goal-test"
    session_id = "sess-test"


class _CapturingAgent:
    """Fanger prompten i stedet for å kalle en modell."""

    captured: dict = {}

    def __init__(self, **kwargs):
        type(self).captured = {"init": kwargs}

    def run_conversation(self, prompt, *, system_message, **kwargs):
        type(self).captured["prompt"] = prompt
        type(self).captured["system_message"] = system_message
        return {"final_response": json.dumps({"status": "PASS", "confidence": 0.9})}

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _pinned_max_age(monkeypatch):
    """Fest foreldelsesgrensen for HELE fila.

    Reviewer 2026-08-11: katalogen her hadde et HARDKODET tidsstempel, og fila
    festet ingenting — så fra doegnet etter ville hver dekningspaastand her
    feile paa foreldelse i stedet for paa det den tester. Den andre testfila
    hadde allerede baade `_fresh()` og en pinning-fixture; denne arvet ingen av
    dem. En tidsinnstilt bombe i testen for en tidsregel.
    """
    monkeypatch.setattr(selector, "MAX_INDEX_AGE_S", 24 * 3600)


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """En ekte katalog på disk + en fanget agent."""
    catalog = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_coverage": "complete",
        "skills": [
            {"name": "neo4j-graph-migration",
             "description": "Migrate Neo4j graphs and rewrite Cypher queries after label renames.",
             "body": "Use MATCH on the old label, copy properties, then drop it.",
             "tags": [], "primary_path": "/skills/neo4j-graph-migration/SKILL.md",
             "primary_root": "hermes_home", "content_md5": "m1", "locations": [],
             "archived": False, "name_collision": False},
            {"name": "react-hooks",
             "description": "Build React components with hooks and effects.",
             "body": "useEffect, useState, useMemo.",
             "tags": [], "primary_path": "/skills/react-hooks/SKILL.md",
             "primary_root": "hermes_home", "content_md5": "m2", "locations": [],
             "archived": False, "name_collision": False},
        ],
    }
    index = tmp_path / "catalog.json"
    index.write_text(json.dumps(catalog), encoding="utf-8")
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setattr(adapter, "DEFAULT_INDEX_FOR_TEST", index, raising=False)
    monkeypatch.setenv("HERMES_SKILL_INDEX", str(index))
    monkeypatch.setenv("HERMES_SKILL_TRACE", str(trace))

    monkeypatch.setattr(adapter, "evaluate_coding_turn",
                        lambda *a, **k: types.SimpleNamespace(admitted=True))
    monkeypatch.setattr(adapter, "default_live_model_resolver", lambda _role: "test-model")
    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = _CapturingAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    _CapturingAgent.captured = {}
    return {"index": index, "trace": trace}


def test_selected_skill_reaches_the_system_prompt(wired):
    """Den valgte skillen står NAVNGITT i prompten modellen faktisk får."""
    out = adapter.run_live_faber_review(
        raw_text="the cypher query is wrong after the neo4j label rename migration",
        envelope=_Envelope(),
    )
    system = _CapturingAgent.captured["system_message"]
    assert "neo4j-graph-migration" in system
    assert "react-hooks" not in system
    assert "/skills/neo4j-graph-migration/SKILL.md" in system
    assert out["status"] == "PASS"


def test_old_claim_is_gone_from_both_prompts(wired):
    """Påstanden «use your own ... skills» skal ikke finnes noe sted lenger.

    Den sto to steder: i _SYSTEM og i brukermeldingen. Å fjerne den ene og la
    den andre stå ville etterlatt nøyaktig den oppfordringen-til-å-huske som
    denne endringen erstatter.
    """
    adapter.run_live_faber_review(raw_text="neo4j cypher label rename", envelope=_Envelope())
    system = _CapturingAgent.captured["system_message"]
    prompt = _CapturingAgent.captured["prompt"]
    assert "memory and skills" not in system
    assert "memory and skills" not in prompt


def test_selection_is_reported_in_the_result(wired):
    """Returverdien bærer valget — for DIREKTE kallere.

    Ærlig avgrensning (reviewer 2026-08-11): den eneste produksjonskalleren,
    `agent/faber_chat_bridge.py`, filtrerer metadata mot en allowlist som ikke
    inneholder disse nøklene, så de når IKKE `faber.readback`. Sporet
    (`test_selection_is_written_to_the_trace`) er den autoritative
    observerbarheten i produksjon; dette er kontrakten for den som kaller
    funksjonen direkte. Å utvide allowlisten hører hjemme i faber_chat_bridge.py
    — en fil denne endringen ikke holder lease på.
    """
    out = adapter.run_live_faber_review(
        raw_text="neo4j cypher label rename migration", envelope=_Envelope())
    assert out["skills_selected"] == ["neo4j-graph-migration"]
    assert out["skill_coverage"] == "complete"
    assert out["skills_considered"] == 2
    # JSON-kontrakten forbyr innhold, ikke provenans.
    assert out["content_included"] is False


def test_selection_is_written_to_the_trace(wired):
    adapter.run_live_faber_review(
        raw_text="neo4j cypher label rename migration", envelope=_Envelope())
    lines = wired["trace"].read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[-1])
    assert record["stage"] == "faber_live_review"
    assert record["selected"][0]["name"] == "neo4j-graph-migration"
    assert record["coverage"] == "complete"


def test_missing_index_does_not_break_the_review(tmp_path, monkeypatch, wired):
    """Uten indeks skal kjeden fortsatt kjøre — og SI at dekningen er ukjent.

    Fail-open på funksjon, fail-closed på påstand: gjennomgangen går videre, men
    prompten advarer eksplisitt mot å konkludere at en skill ikke finnes.
    """
    monkeypatch.setenv("HERMES_SKILL_INDEX", str(tmp_path / "does-not-exist.json"))
    out = adapter.run_live_faber_review(raw_text="neo4j cypher rename", envelope=_Envelope())
    system = _CapturingAgent.captured["system_message"]
    assert "UNKNOWN" in system
    assert "Do not conclude" in system
    assert out["skill_coverage"] == "unknown"
    assert out["status"] == "PASS"


def test_blocked_turn_does_not_select(wired, monkeypatch):
    """Et avvist innspill skal ikke koste en katalogoppslag eller et spor."""
    monkeypatch.setattr(adapter, "evaluate_coding_turn",
                        lambda *a, **k: types.SimpleNamespace(admitted=False))
    out = adapter.run_live_faber_review(raw_text="neo4j cypher", envelope=_Envelope())
    assert out["status"] == "BLOCK"
    assert not wired["trace"].exists()
