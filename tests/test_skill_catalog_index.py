"""Tester for skill_catalog_index (BL-4057).

Tyngdepunktet ligger på DEKNINGSMÅLINGEN, ikke på at skanningen finner filer.
Grunnen: en indeks som teller feil er synlig med en gang, mens en indeks som
rapporterer COMPLETE på en halvlest katalog er usynlig helt til noen bygger en
fravær-påstand på den. Det er det BL-4039 kostet tre reviewer-runder å lære.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.skill_catalog_index import (  # noqa: E402
    Coverage,
    SkillRoot,
    build_index,
    merge,
    parse_frontmatter,
    scan_root,
    weakest,
    write_index,
)


def _skill(root: Path, rel: str, name: str, description: str = "", body: str = "body") -> Path:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8")
    return p


# -- dekning ------------------------------------------------------------


def test_missing_root_is_unknown_not_empty(tmp_path):
    """En rot som ikke finnes har UKJENT omfang — ikke null skills.

    Dette er hele forskjellen mellom «vi fant ingenting» og «det finnes
    ingenting», og den som kollapser de to produserer falske funn.
    """
    cov, entries = scan_root(SkillRoot("gone", tmp_path / "nope", 0))
    assert cov.state is Coverage.UNKNOWN
    assert cov.expected is None
    assert entries == []


def test_fully_read_root_is_complete(tmp_path):
    _skill(tmp_path, "a", "alpha")
    _skill(tmp_path, "b", "beta")
    cov, entries = scan_root(SkillRoot("r", tmp_path, 0))
    assert cov.state is Coverage.COMPLETE
    assert (cov.read, cov.expected) == (2, 2)
    assert len(entries) == 2


def test_unreadable_file_makes_root_partial(tmp_path):
    """Én fil som ikke lar seg lese senker HELE roten til PARTIAL."""
    _skill(tmp_path, "ok", "fine")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_bytes(b"---\n\xff\xfe not utf8\n---\n")
    cov, entries = scan_root(SkillRoot("r", tmp_path, 0))
    assert cov.state is Coverage.PARTIAL
    assert cov.read == 1 and cov.expected == 2
    assert cov.errors and "bad/SKILL.md" in cov.errors[0]
    assert len(entries) == 1


def test_broken_frontmatter_counts_as_read_error_not_empty_metadata(tmp_path):
    """Ødelagt frontmatter er en LESEFEIL, ikke en fil uten metadata.

    Regresjonen dette hindrer: hvis parse-feil ble til `{}`, ville fila blitt
    indeksert med tomt navn og roten rapportert COMPLETE — altså en feil som
    forsvinner inn i sitt eget resultat.
    """
    d = tmp_path / "broken"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: x\n  bad: [unclosed\n---\nbody\n", encoding="utf-8")
    cov, _ = scan_root(SkillRoot("r", tmp_path, 0))
    assert cov.state is Coverage.PARTIAL
    assert cov.read == 0
    assert "frontmatter" in cov.errors[0]


def test_archive_is_reported_not_silently_dropped(tmp_path):
    """Utelatte arkiv-skills er et MÅLT valg, ikke et stille kutt."""
    _skill(tmp_path, "live", "live-one")
    _skill(tmp_path, ".archive/old", "old-one")
    cov, entries = scan_root(SkillRoot("r", tmp_path, 0))
    assert cov.state is Coverage.COMPLETE  # begge er håndtert
    assert cov.read == 2
    assert [e.name for e in entries] == ["live-one"]
    assert ".archive/" in cov.note or "archive" in cov.note

    cov2, entries2 = scan_root(SkillRoot("r", tmp_path, 0), include_archive=True)
    assert {e.name for e in entries2} == {"live-one", "old-one"}
    assert cov2.state is Coverage.COMPLETE


# -- svakeste ledd ------------------------------------------------------


def test_weakest_link_wins():
    assert weakest([Coverage.COMPLETE, Coverage.COMPLETE]) is Coverage.COMPLETE
    assert weakest([Coverage.COMPLETE, Coverage.PARTIAL]) is Coverage.PARTIAL
    assert weakest([Coverage.PARTIAL, Coverage.UNKNOWN]) is Coverage.UNKNOWN


def test_empty_coverage_is_unknown_not_complete():
    """`all([]) is True` er fella. Ingen røtter lest er det MOTSATTE av alt lest."""
    assert weakest([]) is Coverage.UNKNOWN


def test_one_missing_root_infects_whole_catalog(tmp_path):
    """En manglende rot smitter: skillen som «mangler» kan ligge nettopp der."""
    good = tmp_path / "good"
    _skill(good, "a", "alpha")
    index = build_index([SkillRoot("good", good, 0), SkillRoot("gone", tmp_path / "nope", 1)])
    assert index["catalog_coverage"] == "unknown"
    assert index["catalog_coverage_complete"] is False
    assert index["skill_count"] == 1  # katalogen er brukbar, bare ikke uttømmende


# -- sammenslåing -------------------------------------------------------


def test_same_content_in_two_roots_merges_keeping_both_locations(tmp_path):
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    _skill(r1, "dup", "dup", body="identical")
    _skill(r2, "dup", "dup", body="identical")
    index = build_index([SkillRoot("r1", r1, 0), SkillRoot("r2", r2, 1)])
    assert index["skill_count"] == 1
    entry = index["skills"][0]
    assert entry["primary_root"] == "r1"  # presedens avgjør primær
    assert len(entry["locations"]) == 2
    assert entry["name_collision"] is False


def test_same_name_different_content_keeps_both_and_flags(tmp_path):
    """Drift slås ALDRI sammen i stillhet — å velge en vinner er et silent cap."""
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    _skill(r1, "x", "twin", body="version A")
    _skill(r2, "x", "twin", body="version B")
    index = build_index([SkillRoot("r1", r1, 0), SkillRoot("r2", r2, 1)])
    assert index["skill_count"] == 2
    assert index["name_collisions"] == ["twin"]
    assert all(s["name_collision"] for s in index["skills"])


def test_precedence_picks_primary_but_never_discards(tmp_path):
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    _skill(r1, "s", "same", body="shared")
    _skill(r2, "s", "same", body="shared")
    # Lav presedens først i lista skal ikke endre utfallet.
    index = build_index([SkillRoot("r2", r2, 5), SkillRoot("r1", r1, 0)])
    entry = index["skills"][0]
    assert entry["primary_root"] == "r1"
    assert {loc["root"] for loc in entry["locations"]} == {"r1", "r2"}


# -- frontmatter --------------------------------------------------------


def test_parse_frontmatter_variants():
    assert parse_frontmatter("no frontmatter here") == {}
    assert parse_frontmatter("---\nname: a\n---\nbody")["name"] == "a"
    multiline = "---\nname: a\ndescription: |\n  line one\n  line two\n---\nbody"
    assert "line one" in parse_frontmatter(multiline)["description"]
    with pytest.raises(ValueError):
        parse_frontmatter("---\nname: a\nnever closed")


def test_frontmatter_that_is_not_a_mapping_raises():
    with pytest.raises(ValueError):
        parse_frontmatter("---\n- just\n- a list\n---\nbody")


# -- utdata -------------------------------------------------------------


def test_write_index_is_atomic_and_readable(tmp_path):
    # Kanoniske rot-nøkler, ellers slår omfangsvakten inn (scope_narrowed) og
    # testen ville målt noe annet enn atomisk skriving.
    roots = []
    for i, key in enumerate(("repo_active", "repo_optional", "hermes_home",
                             "hermes_gui", "mwp")):
        d = tmp_path / key
        _skill(d, f"s{i}", f"skill-{i}", "does alpha things")
        roots.append(SkillRoot(key, d, i))
    index = build_index(roots)
    out = write_index(index, tmp_path / "sub" / "catalog.json")
    assert out.exists()
    assert not out.with_suffix(out.suffix + ".tmp").exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["skill_count"] == 5
    assert loaded["catalog_coverage"] == "complete"


def test_merge_is_deterministic(tmp_path):
    r = tmp_path / "r"
    for n in ("c", "a", "b"):
        _skill(r, n, n)
    roots = [SkillRoot("r", r, 0)]
    first = [e.name for e in merge([e for _, es in [scan_root(roots[0])] for e in es], roots)]
    second = [e.name for e in merge([e for _, es in [scan_root(roots[0])] for e in es], roots)]
    assert first == second == ["a", "b", "c"]


# -- reviewer-runde 1, 2026-08-11: regresjonsvakter ---------------------


def test_unreadable_subtree_is_a_read_error_not_an_invisible_skill(tmp_path):
    """BLOCK-2: invarianten beseiret ved roten.

    Målt av reviewer: en katalog med mode 000 var usynlig for BÅDE `expected` og
    `read`, fordi `rglob` svelger OSError. Roten rapporterte COMPLETE med
    `errors: ()` mens en skill lå ulest inni — altså kunne en MISSING-påstand
    utstedes mot en skill som fantes.
    """
    import os as _os

    _skill(tmp_path, "visible", "visible-one")
    locked = tmp_path / "locked"
    (locked / "inner").mkdir(parents=True)
    (locked / "inner" / "SKILL.md").write_text("---\nname: hidden\n---\nbody\n",
                                               encoding="utf-8")
    _os.chmod(locked, 0o000)
    try:
        cov, entries = scan_root(SkillRoot("r", tmp_path, 0))
        if _os.geteuid() == 0:
            pytest.skip("root ignorerer katalogpermisjoner")
        assert cov.state is Coverage.PARTIAL
        assert cov.errors
        assert [e.name for e in entries] == ["visible-one"]
    finally:
        _os.chmod(locked, 0o755)


def test_narrowed_root_set_is_not_complete(tmp_path):
    """Finding 8: dybde var målt, omfang var antatt.

    `build_index([repo_active])` ga COMPLETE med 81 skills mens 624 lå i de fire
    andre røttene. Å ha lest alt av det man valgte å se på, er ikke å ha lest alt.
    """
    r = tmp_path / "one"
    _skill(r, "a", "alpha")
    index = build_index([SkillRoot("repo_active", r, 0)])
    assert index["catalog_coverage"] == "partial"
    assert index["scope_narrowed"] is True
    assert "hermes_home" in index["roots_missing"]


def test_full_canonical_root_set_can_be_complete(tmp_path):
    """Motprøven: omfangsvakten må ikke gjøre COMPLETE uoppnåelig."""
    roots = []
    for i, key in enumerate(("repo_active", "repo_optional", "hermes_home",
                             "hermes_gui", "mwp")):
        d = tmp_path / key
        _skill(d, f"s{i}", f"skill-{i}")
        roots.append(SkillRoot(key, d, i))
    index = build_index(roots)
    assert index["catalog_coverage"] == "complete"
    assert index["scope_narrowed"] is False
    assert index["roots_missing"] == []


def test_dedup_keeps_a_losing_name_findable_as_alias(tmp_path):
    """Finding 10: md5-dedup kunne slette et distinkt navn i stillhet."""
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    for root, rel in ((r1, "alpha-tool"), (r2, "beta-tool")):
        d = root / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("same bytes, no frontmatter name\n", encoding="utf-8")
    index = build_index([SkillRoot("r1", r1, 0), SkillRoot("r2", r2, 1)])
    assert index["skill_count"] == 1
    entry = index["skills"][0]
    assert entry["name"] == "alpha-tool"
    assert "beta-tool" in entry["aliases"]


def test_two_root_keys_on_one_path_is_not_full_coverage(tmp_path):
    """Fem nøkler, fire kataloger — det er ikke fem røtter.

    Målt 2026-08-11: under `HERMES_HOME=~/.hermes-gui` (som den eksisterende
    faber-cronen bruker) løser `hermes_home` og `hermes_gui` til SAMME sti, og
    `~/.hermes/skills` — 461 skills — blir aldri skannet. Uten denne vakten
    ville katalogen meldt COMPLETE med et hull på to tredjedeler.
    """
    shared = tmp_path / "shared"
    _skill(shared, "a", "alpha")
    roots = []
    for i, key in enumerate(("repo_active", "repo_optional", "hermes_home",
                             "hermes_gui", "mwp")):
        # hermes_home og hermes_gui peker bevisst på samme katalog.
        d = shared if key in ("hermes_home", "hermes_gui") else tmp_path / key
        if d is not shared:
            _skill(d, f"s{i}", f"skill-{i}")
        roots.append(SkillRoot(key, d, i))
    index = build_index(roots)
    assert index["catalog_coverage"] == "partial"
    assert index["scope_narrowed"] is True
    assert index["roots_missing"] == []          # alle fem nøkler ER til stede
    assert index["root_path_collisions"]          # ...men to deler katalog
    assert index["root_path_collisions"][0]["keys"] == ["hermes_gui", "hermes_home"]


def test_nested_root_is_reported_but_does_not_degrade_coverage(tmp_path):
    """En nøstet rot dobbelt-leser, den under-leser ikke.

    Derfor rapporteres den uten å senke dekningen: `files_seen` blir høy, men
    merge() slår de doble funnene sammen på innhold, og ingen skill blir ulest.
    Å degradere her ville gjort PARTIAL til støy — og PARTIAL må bety noe.
    """
    outer = tmp_path / "outer"
    inner = outer / "nested"
    _skill(outer, "a", "alpha")
    _skill(inner, "b", "beta")
    index = build_index([SkillRoot("repo_active", outer, 0),
                         SkillRoot("repo_optional", inner, 1),
                         SkillRoot("hermes_home", tmp_path / "h", 2),
                         SkillRoot("hermes_gui", tmp_path / "g", 3),
                         SkillRoot("mwp", tmp_path / "m", 4)])
    assert index["root_nesting"]
    assert index["root_nesting"][0]["inner"] == "repo_optional"
    assert index["root_nesting"][0]["outer"] == "repo_active"
    # beta ble lest to ganger, men finnes bare én gang i katalogen.
    assert sorted(s["name"] for s in index["skills"]) == ["alpha", "beta"]


def test_symlinked_subdirectory_is_read_not_silently_skipped(tmp_path):
    """Siste form av blindsonen fra funn 2 — symlenke i stedet for permission-bit.

    Med followlinks=False var `read == expected`, `errors: ()`, COMPLETE — og
    skillen bak lenken simpelthen borte. En MISSING-påstand mot den ville vært
    et falskt funn.
    """
    import os as _os

    root = tmp_path / "root"
    _skill(root, "direct", "direct-one")
    elsewhere = tmp_path / "elsewhere"
    _skill(elsewhere, "linked", "behind-symlink")
    _os.symlink(elsewhere / "linked", root / "linked-in")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    assert cov.state is Coverage.COMPLETE
    assert cov.errors == ()
    assert sorted(e.name for e in entries) == ["behind-symlink", "direct-one"]


def test_symlink_cycle_terminates(tmp_path):
    """followlinks uten syklusvern henger for alltid på én lenke."""
    import os as _os

    root = tmp_path / "root"
    _skill(root, "a", "alpha")
    _os.symlink(root, root / "loop")          # a/loop -> a
    inner = root / "deep"
    inner.mkdir()
    _os.symlink(root, inner / "back")          # a/deep/back -> a

    cov, entries = scan_root(SkillRoot("r", root, 0))   # må terminere
    assert cov.state is Coverage.COMPLETE
    assert [e.name for e in entries] == ["alpha"]       # alpha telles ÉN gang


def test_two_symlinks_to_the_same_skill_are_one_entry(tmp_path):
    """Delt undertre er allerede lest — ikke et hull, og ikke to skills."""
    import os as _os

    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "shared"
    _skill(target, "s", "shared-one")
    _os.symlink(target / "s", root / "link-a")
    _os.symlink(target / "s", root / "link-b")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    assert cov.state is Coverage.COMPLETE
    assert [e.name for e in entries] == ["shared-one"]


def test_out_of_root_link_is_recorded_as_provenance_not_degradation(tmp_path):
    """Motstykket til scope_narrowed: «jeg så på MER enn roten».

    En SKILL.md hvor som helst på filsystemet havner nå under en kanonisk
    rot-nøkkel, og navn + beskrivelse går inn i den governede reviewerens
    systemprompt. Dekningen er fortsatt sann — så dette rapporteres, det
    degraderer ikke.
    """
    import os as _os

    root = tmp_path / "root"
    _skill(root, "own", "own-skill")
    foreign = tmp_path / "foreign"
    _skill(foreign, "f", "foreign-skill")
    _os.symlink(foreign / "f", root / "link")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    assert cov.state is Coverage.COMPLETE          # ikke degradert
    assert sorted(e.name for e in entries) == ["foreign-skill", "own-skill"]
    assert cov.out_of_root                          # ...men synlig
    assert "UTENFOR roten" in cov.note


def test_parent_link_is_refused_without_losing_coverage(tmp_path):
    """En forelder-lenke gjør den timesvis cronen til en filsystem-traversering.

    NB på begrunnelsen: å nekte taper faktisk NOE — en forelder inneholder også
    alt ved siden av roten, og de søsken-skillene blir ikke lest (testen under
    pinner nettopp det). Grunnen dette likevel ikke senker dekningen er at det
    deklarerte omfanget ER de fem røttene: dette er en OMFANGSBESLUTNING som
    noteres, ikke et målehull. Reviewer 2026-08-11 felte den forrige, sterkere
    formuleringen.
    """
    import os as _os

    parent = tmp_path / "parent"
    root = parent / "root"
    _skill(root, "own", "own-skill")
    _skill(parent / "sibling", "s", "sibling-skill")
    _os.symlink(parent, root / "up")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    assert cov.state is Coverage.COMPLETE
    assert [e.name for e in entries] == ["own-skill"]     # ikke sugd inn
    assert cov.refused_links
    assert "forelder-lenke" in cov.note
    assert "utvidet" in cov.note          # omfangsbeslutning, ikke dekningspåstand
    assert "roten dekker dem" not in cov.note


def test_link_to_home_does_not_crawl_the_home_directory(tmp_path):
    """Den operasjonelle faren, direkte: ln -s <forelder> inne i roten."""
    import os as _os

    big = tmp_path / "big"
    for i in range(30):
        _skill(big, f"s{i}", f"noise-{i}")
    root = big / "root"
    _skill(root, "own", "own-skill")
    _os.symlink(big, root / "home-link")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    assert [e.name for e in entries] == ["own-skill"]
    assert cov.read == 1 and cov.expected == 1


def test_symlinked_SKILL_FILE_is_recorded_as_out_of_root(tmp_path):
    """os.walk eksponerer bare KATALOGERS lenke-status — filer slapp forbi.

    Reviewer 2026-08-11: `root/sneak/SKILL.md -> /andre/sted/SKILL.md` ble lest,
    indeksert under en kanonisk rot-nøkkel og var valgbar for den governede
    systemprompten, mens out_of_root rapporterte ingenting. Et provenansfelt som
    ikke dekker alle veier inn er verre enn ingen — det blir trodd.
    """
    import os as _os

    root = tmp_path / "root"
    _skill(root, "ok", "ok-skill")
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("---\nname: foreign-file-skill\n---\nbody\n",
                                      encoding="utf-8")
    sneak = root / "sneak"
    sneak.mkdir()
    _os.symlink(foreign / "SKILL.md", sneak / "SKILL.md")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    assert sorted(e.name for e in entries) == ["foreign-file-skill", "ok-skill"]
    assert cov.out_of_root, "en symlenket SKILL.md-FIL må også telle som utenfor roten"
    assert any("foreign" in t for t in cov.out_of_root)


def test_parent_link_refusal_does_lose_sibling_skills(tmp_path):
    """Pinner det motbeviset reviewer brukte til å felle kommentaren.

    Testen finnes for at ingen skal gjeninnføre «roten dekker dem»: den gjør det
    tapte eksplisitt, slik at policyen forsvares på riktig grunnlag.
    """
    import os as _os

    parent = tmp_path / "parent"
    root = parent / "root"
    _skill(root, "own", "own-skill")
    for i in range(3):
        _skill(parent / f"sib{i}", "s", f"sibling-{i}")
    _os.symlink(parent, root / "up")

    cov, entries = scan_root(SkillRoot("r", root, 0))
    names = [e.name for e in entries]
    assert names == ["own-skill"]
    # Disse er nåbare fra innsiden av roten og blir IKKE lest. Det er prisen,
    # og den er bevisst.
    assert not any(n.startswith("sibling-") for n in names)
    assert cov.state is Coverage.COMPLETE
