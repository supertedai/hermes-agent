"""Tester for skill_selector (BL-4057).

Den viktigste testen i fila er `test_cannot_report_missing_under_partial_coverage`.
Alt annet er seleksjonskvalitet; den ene er invarianten fra BL-4039, og den er
grunnen til at `report_missing()` returnerer en tredje verdi i stedet for et
boolsk svar.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import agent.skill_selector as selector  # noqa: E402
from agent.skill_selector import (  # noqa: E402
    UNRESOLVED,
    SkillCatalog,
    render_for_prompt,
    report_missing,
    select_for_task,
    trace,
)


def _fresh() -> str:
    """Alltid et FERSKT tidsstempel.

    En hardkodet dato her ville vaert en tidsinnstilt bombe: foreldelsesregelen
    (MAX_INDEX_AGE_S) degraderer COMPLETE til PARTIAL etter et doegn, saa hver
    dekningstest ville begynt aa feile dagen etter at den ble skrevet — og feilet
    paa noe helt annet enn det den tester.
    """
    return datetime.now(timezone.utc).isoformat()


def _index(skills, coverage="complete"):
    return {
        "version": 1,
        "generated_at": _fresh(),
        "catalog_coverage": coverage,
        "catalog_coverage_complete": coverage == "complete",
        "skills": [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "tags": s.get("tags", []),
                "primary_path": s.get("path", f"/skills/{s['name']}/SKILL.md"),
                "primary_root": s.get("root", "test"),
                "content_md5": s.get("md5", s["name"]),
                "locations": [],
                "archived": False,
                "name_collision": s.get("collision", False),
            }
            for s in skills
        ],
    }


def _write(tmp_path, index) -> Path:
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(index), encoding="utf-8")
    return p


CORPUS = [
    {"name": "neo4j-graph-migration",
     "description": "Migrate Neo4j graph schemas, rewrite Cypher queries, handle label changes."},
    {"name": "docker-compose-deploy",
     "description": "Deploy and troubleshoot Docker Compose stacks, container health, port bindings."},
    {"name": "pytest-fixtures",
     "description": "Write and refactor pytest fixtures, parametrize tests, manage conftest scope."},
    {"name": "react-hooks",
     "description": "Build React components with hooks, manage effects and state."},
]


# -- INVARIANTEN --------------------------------------------------------


def test_cannot_report_missing_under_partial_coverage(tmp_path):
    """BL-4039: uten FULL lesning kan ingenting kalles manglende.

    Samme spørring, samme tomme treffliste — men under PARTIAL er svaret
    UNRESOLVED, ikke MISSING. Det er forskjellen på «vi vet ikke» og et falskt
    funn, og den må være strukturell fordi de to ser like ut.
    """
    partial = _write(tmp_path, _index(CORPUS, coverage="partial"))
    sel = SkillCatalog.load(partial).select("quantum chromodynamics lattice")
    assert sel.selected == ()
    assert report_missing(sel) is UNRESOLVED


def test_can_report_missing_only_under_complete_coverage(tmp_path):
    full = _write(tmp_path, _index(CORPUS, coverage="complete"))
    sel = SkillCatalog.load(full).select("quantum chromodynamics lattice")
    assert sel.selected == ()
    assert report_missing(sel) == "MISSING"


def test_unknown_coverage_also_blocks_missing(tmp_path):
    unknown = _write(tmp_path, _index(CORPUS, coverage="unknown"))
    sel = SkillCatalog.load(unknown).select("quantum chromodynamics lattice")
    assert report_missing(sel) is UNRESOLVED


def test_absent_index_is_unknown_not_empty_catalog(tmp_path):
    """En ubygget indeks må ikke lese som «det finnes ingen skills»."""
    catalog = SkillCatalog.load(tmp_path / "never-built.json")
    assert catalog.coverage == "unknown"
    assert catalog.size == 0
    sel = catalog.select("anything at all")
    assert report_missing(sel) is UNRESOLVED
    assert catalog.load_error


def test_corrupt_index_is_unknown_not_crash(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    catalog = SkillCatalog.load(p)
    assert catalog.coverage == "unknown"
    assert report_missing(catalog.select("x")) is UNRESOLVED


def test_unresolved_is_not_falsy_by_accident():
    """UNRESOLVED må ikke kollapse til «nei» i en if-test."""
    assert bool(UNRESOLVED) is True
    assert UNRESOLVED != "MISSING"


# -- seleksjonskvalitet -------------------------------------------------


def test_selects_the_right_skill_for_a_graph_task(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("rewrite the Cypher query after the Neo4j label rename")
    assert sel.top is not None
    assert sel.top.name == "neo4j-graph-migration"
    assert report_missing(sel) == "PRESENT"


def test_selects_the_right_skill_for_a_container_task(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("the docker compose stack has an unhealthy container")
    assert sel.top.name == "docker-compose-deploy"


def test_matched_terms_make_the_score_auditable(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("pytest fixtures conftest")
    assert sel.top.name == "pytest-fixtures"
    assert "pytest" in sel.top.matched_terms
    assert sel.top.score > 0


def test_ranking_is_deterministic(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    catalog = SkillCatalog.load(p)
    a = [s.name for s in catalog.select("docker container deploy").selected]
    b = [s.name for s in catalog.select("docker container deploy").selected]
    assert a == b and a


def test_limit_is_respected(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("docker neo4j pytest react", limit=2, min_score=0.0)
    assert len(sel.selected) == 2


def test_empty_query_yields_no_selection_but_keeps_coverage(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("   ")
    assert sel.selected == ()
    assert sel.coverage == "complete"
    assert sel.note


def test_stopwords_do_not_drive_selection(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("how do I use the thing with it")
    assert sel.selected == ()


# -- observerbarhet -----------------------------------------------------


def test_trace_records_the_selection(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    tr = tmp_path / "trace.jsonl"
    sel = SkillCatalog.load(p).select("neo4j cypher migration")
    written = trace(sel, stage="unit", path=tr)
    assert written == tr
    record = json.loads(tr.read_text(encoding="utf-8").strip())
    assert record["stage"] == "unit"
    assert record["selected"][0]["name"] == "neo4j-graph-migration"
    assert record["coverage"] == "complete"
    assert record["considered"] == len(CORPUS)


def test_trace_appends(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    tr = tmp_path / "trace.jsonl"
    catalog = SkillCatalog.load(p)
    trace(catalog.select("docker"), stage="one", path=tr)
    trace(catalog.select("pytest"), stage="two", path=tr)
    assert len(tr.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_trace_failure_never_raises(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("docker")
    # En katalog som sti er ikke skrivbar som fil.
    assert trace(sel, stage="x", path=tmp_path) is None


def test_select_for_task_is_one_call(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    tr = tmp_path / "t.jsonl"
    sel = select_for_task("neo4j cypher label rename", stage="step3",
                          index_path=p, trace_path=tr)
    assert sel.top.name == "neo4j-graph-migration"
    assert json.loads(tr.read_text(encoding="utf-8").strip())["stage"] == "step3"


# -- prompt-tekst -------------------------------------------------------


def test_prompt_names_the_selected_skills(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    text = render_for_prompt(SkillCatalog.load(p).select("neo4j cypher"))
    assert "neo4j-graph-migration" in text
    assert "path:" in text


def test_prompt_states_measured_absence_under_complete(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    text = render_for_prompt(SkillCatalog.load(p).select("lattice qcd"))
    assert "measured absence" in text


def test_prompt_warns_instead_of_claiming_absence_under_partial(tmp_path):
    """Prompten må ikke la modellen tro at en ufullstendig liste er uttømmende."""
    p = _write(tmp_path, _index(CORPUS, coverage="partial"))
    text = render_for_prompt(SkillCatalog.load(p).select("lattice qcd"))
    assert "PARTIAL" in text
    assert "Do not conclude" in text


def test_prompt_flags_incomplete_coverage_even_with_hits(tmp_path):
    p = _write(tmp_path, _index(CORPUS, coverage="partial"))
    text = render_for_prompt(SkillCatalog.load(p).select("neo4j cypher"))
    assert "neo4j-graph-migration" in text
    assert "not COMPLETE" in text


def test_prompt_is_bounded(tmp_path):
    p = _write(tmp_path, _index(CORPUS))
    text = render_for_prompt(SkillCatalog.load(p).select("docker neo4j pytest", limit=3),
                             max_chars=80)
    assert len(text) <= 80


# -- foreldelse ---------------------------------------------------------


def _aged(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


@pytest.fixture(autouse=True)
def _pinned_max_age(monkeypatch):
    """Fest foreldelsesgrensen til 24 t for HELE fila.

    Ellers arver testene HERMES_SKILL_INDEX_MAX_AGE_S fra miljoeet de kjoerer i,
    og en CI-runner som setter den lavt ville faatt «fersk indeks»-testen til aa
    feile paa noe den ikke tester.
    """
    monkeypatch.setattr(selector, "MAX_INDEX_AGE_S", 24 * 3600)


def test_stale_index_loses_its_complete_claim(tmp_path):
    """En gammel indeks får ikke fortsette å påstå COMPLETE.

    Uten dette ville en indeks bygget én gang si «vi leste hele katalogen» i det
    uendelige, mens noen installerte femti nye skills — og en fravær-påstand
    bygget på den ville vært falsk uten at noe feilet.
    """
    ix = _index(CORPUS, coverage="complete")
    ix["generated_at"] = _aged(72)
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert catalog.is_stale
    assert catalog.coverage == "partial"
    assert report_missing(catalog.select("lattice qcd")) is UNRESOLVED


def test_fresh_index_keeps_complete(tmp_path):
    ix = _index(CORPUS, coverage="complete")
    ix["generated_at"] = _aged(1)
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert not catalog.is_stale
    assert catalog.coverage == "complete"
    assert report_missing(catalog.select("lattice qcd")) == "MISSING"


def test_staleness_does_not_upgrade_a_partial_index(tmp_path):
    """Foreldelse kan bare senke dekningen, aldri heve den."""
    ix = _index(CORPUS, coverage="unknown")
    ix["generated_at"] = _aged(72)
    assert SkillCatalog.load(_write(tmp_path, ix)).coverage == "unknown"


def test_stale_index_says_so_in_the_note(tmp_path):
    ix = _index(CORPUS, coverage="complete")
    ix["generated_at"] = _aged(48)
    sel = SkillCatalog.load(_write(tmp_path, ix)).select("neo4j cypher")
    assert "gammel" in sel.note
    assert "skill_catalog_index" in sel.note


def test_selection_still_works_when_stale(tmp_path):
    """Foreldelse svekker PÅSTANDEN, ikke funksjonen — skills velges fortsatt."""
    ix = _index(CORPUS, coverage="complete")
    ix["generated_at"] = _aged(72)
    sel = SkillCatalog.load(_write(tmp_path, ix)).select("neo4j cypher label")
    assert sel.top.name == "neo4j-graph-migration"
    assert sel.coverage == "partial"


# -- reviewer-runde 1, 2026-08-11: regresjonsvakter ---------------------


def test_no_usable_terms_is_unresolved_not_measured_absence(tmp_path):
    """BLOCK-3: fraværet var av SPØRRING, ikke av katalog.

    Målt av reviewer gjennom den ekte adapteren: en tur med bare tegnsetting
    ga «the catalog was read in full (705 skills), so this is a measured
    absence». Full dekning gjør ikke et ikke-stilt spørsmål besvart.
    """
    p = _write(tmp_path, _index(CORPUS, coverage="complete"))
    catalog = SkillCatalog.load(p)
    for junk in ("{ } ; ++ -- >>> ### |||", "the and or of to in on", "日本語のみ"):
        sel = catalog.select(junk)
        assert sel.queryable is False, junk
        assert report_missing(sel) is UNRESOLVED, junk
        assert "measured absence" not in render_for_prompt(sel), junk


def test_real_query_with_no_hits_is_still_a_measured_absence(tmp_path):
    """Motprøven: queryable-vakten må ikke svelge et EKTE målt fravær."""
    p = _write(tmp_path, _index(CORPUS, coverage="complete"))
    sel = SkillCatalog.load(p).select("quantum chromodynamics lattice")
    assert sel.queryable is True
    assert report_missing(sel) == "MISSING"


def test_index_with_non_utf8_bytes_is_unknown_not_raise(tmp_path):
    """BLOCK-1: UnicodeDecodeError slapp ut av den governede stien."""
    p = tmp_path / "bad.json"
    p.write_bytes(b'{"catalog_coverage":"complete","skills":[],"x":"\xff\xfe"}')
    catalog = SkillCatalog.load(p)
    assert catalog.coverage == "unknown"
    assert report_missing(catalog.select("docker")) is UNRESOLVED


def test_index_with_malformed_skills_shape_is_unknown_not_raise(tmp_path):
    """BLOCK-1: `skills` som ikke er dicts ga AttributeError under indeksering."""
    for bad in ([1, 2, 3], "not a list", [{"name": "ok"}, "bare string"]):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"catalog_coverage": "complete", "skills": bad}),
                     encoding="utf-8")
        catalog = SkillCatalog.load(p)
        assert catalog.coverage == "unknown", bad
        assert report_missing(catalog.select("docker")) is UNRESOLVED, bad


def test_index_without_timestamp_loses_complete(tmp_path):
    """Finding 7: ferskhet man ikke kan etterprøve er ikke ferskhet.

    Uten dette kunne foreldelsesregelen omgås ved å FJERNE beviset for alder.
    """
    ix = _index(CORPUS, coverage="complete")
    ix.pop("generated_at")
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert catalog.age_seconds is None
    assert catalog.is_stale is True
    assert catalog.coverage == "partial"
    assert report_missing(catalog.select("lattice qcd")) is UNRESOLVED


def test_unparseable_timestamp_loses_complete(tmp_path):
    ix = _index(CORPUS, coverage="complete")
    ix["generated_at"] = "not-a-date"
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert catalog.is_stale is True
    assert catalog.coverage == "partial"


def test_malformed_env_does_not_break_import():
    """Finding 11: en skrivefeil i miljøet skal ikke felle den governede stien."""
    from agent.skill_selector import _int_env
    assert _int_env("HERMES_NONEXISTENT_XYZ", 42) == 42
    import os
    os.environ["HERMES_BOGUS_TEST_VAR"] = "not-a-number"
    try:
        assert _int_env("HERMES_BOGUS_TEST_VAR", 99) == 99
    finally:
        del os.environ["HERMES_BOGUS_TEST_VAR"]


def test_trace_does_not_persist_raw_turn_text(tmp_path):
    """Finding 9: sporet arkiverte opptil 400 tegn av turen — muligens en nøkkel."""
    p = _write(tmp_path, _index(CORPUS))
    tr = tmp_path / "trace.jsonl"
    secret = "docker deploy AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCY"
    trace(SkillCatalog.load(p).select(secret), stage="x", path=tr)
    written = tr.read_text(encoding="utf-8")
    assert "wJalrXUtnFEMI" not in written
    assert "AWS_SECRET_ACCESS_KEY" not in written
    record = json.loads(written.strip())
    assert len(record["query_sha256_16"]) == 16
    assert record["query_chars"] == len(secret)
    # ...men valget er fortsatt etterprøvbart.
    assert record["selected"][0]["name"] == "docker-compose-deploy"


def test_matched_terms_cannot_leak_a_secret(tmp_path):
    """matched_terms er snittet med katalogens ordforråd — trygt ved konstruksjon."""
    p = _write(tmp_path, _index(CORPUS))
    sel = SkillCatalog.load(p).select("docker hunter2 correcthorsebatterystaple")
    assert sel.top is not None
    assert "hunter2" not in sel.top.matched_terms
    assert "correcthorsebatterystaple" not in sel.top.matched_terms


# -- reviewer-runde 2, 2026-08-11 --------------------------------------


def test_alias_is_findable_not_a_measured_absence(tmp_path):
    """Gjenåpnet funn 10: indekseren SKREV aliases, selektoren leste dem aldri.

    Navnet lå på disk OG i indeksen, og fikk likevel «measured absence». Å skrive
    et felt ingen leser lukker ikke hullet — det dokumenterer det.
    """
    ix = _index([{"name": "alpha-tool", "description": "does alpha things"}])
    ix["skills"][0]["aliases"] = ["beta-tool"]
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    sel = catalog.select("beta-tool")
    assert report_missing(sel) == "PRESENT"
    assert sel.top.name == "alpha-tool"
    assert "measured absence" not in render_for_prompt(sel)


def test_non_string_index_fields_do_not_raise(tmp_path):
    """Residual 1: formvalideringen var toppnivå; `name: 123` kastet fortsatt.

    Adapteren fanget det, men select_for_task og CLI-en gjorde det ikke. En
    indeksfil er data utenfra og skal ikke kunne felle en kaller på feil type.
    """
    ix = _index(CORPUS)
    ix["skills"][0]["name"] = 123
    ix["skills"][1]["tags"] = [1, 2, 3]
    ix["skills"][2]["body"] = {"not": "a string"}
    ix["skills"][3]["description"] = None
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert catalog.size == 4
    sel = catalog.select("docker compose container")   # må ikke kaste
    assert report_missing(sel) in ("PRESENT", "MISSING")


def test_future_dated_index_is_not_fresh(tmp_path):
    """Residual 2: en klokke som peker feil vei er ikke et ferskhetsbevis."""
    ix = _index(CORPUS, coverage="complete")
    ix["generated_at"] = _aged(-24 * 3650)      # ti år inn i framtida
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert catalog.age_seconds < 0
    assert catalog.is_stale is True
    assert catalog.coverage == "partial"
    assert report_missing(catalog.select("lattice qcd")) is UNRESOLVED


def test_selector_honours_scope_narrowed_from_the_index(tmp_path):
    """Residual 3: et COMPLETE med scope_narrowed satt er selvmotsigende."""
    ix = _index(CORPUS, coverage="complete")
    ix["scope_narrowed"] = True
    ix["roots_missing"] = ["hermes_home"]
    catalog = SkillCatalog.load(_write(tmp_path, ix))
    assert catalog.coverage == "partial"
    assert report_missing(catalog.select("lattice qcd")) is UNRESOLVED
