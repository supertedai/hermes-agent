"""BL-4050 steg 8: utfoereren maaler seg selv, og maalingen er ikke et sitat.

Testene er skrevet som ATFERDSTESTER paa den haandhevede stien: en klasse-nivaa-test
kan ikke innfri en paastand om hva kjeden gjoer (BL-4029s egen laerdom fra L4). Der
det er mulig gaar de gjennom :class:`GovernedCodeRunner`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.code_workflow import (
    FaberGoal,
    GoalState,
    GovernedCodeRunner,
    PreflightInput,
    PreflightResult,
    PreflightStatus,
    ReviewEvidence,
    ReviewVerdict,
    ScopeBudget,
)
from agent.faber_implementer import (
    CortexPatchGenerator,
    DesignRecord,
    DesignStore,
    FaberImplementer,
    ImplementationBlocked,
    ProposedPatch,
    diff_id_for,
    measure_blast_radius,
    parse_patch_response,
    _redact,
)


# ------------------------------------------------------------------ riggen ---


class StubGenerator:
    """Generator som returnerer et fast forslag. Ingen nettverk, ingen modell."""

    def __init__(self, patch: ProposedPatch):
        self.patch = patch
        self.calls: list[tuple[DesignRecord, dict]] = []

    def generate(self, design, pre_images, *, budget):
        self.calls.append((design, dict(pre_images)))
        return self.patch


def design_record(tests=("tests/test_x.py",), targets=("a.py",)) -> DesignRecord:
    return DesignRecord(
        goal_id="g1",
        design="add a greeting function",
        target_files=tuple(targets),
        tests=tuple(tests),
        acceptance="tests/test_x.py passes",
        cad_ref="CAD-M",
        adr_ref="ADR-062",
        bl_ref="BL-4050",
    )


def green_runner(command, cwd, timeout):
    return 0, "1 passed in 0.01s"


def red_runner(command, cwd, timeout):
    return 1, "E   assert False\n1 failed in 0.01s"


def implementer(tmp_path: Path, patch: ProposedPatch, *, lease=("a.py",),
                budget=None, command_runner=green_runner, design=None) -> FaberImplementer:
    # Designets testmaal valideres nå mot disk, saa riggen maa faktisk ha det.
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    return FaberImplementer(
        goal_id="g1",
        repo_root=tmp_path,
        lease_set=lease,
        design=design or design_record(),
        design_store=DesignStore(tmp_path / "designs"),
        generator=StubGenerator(patch),
        scope_budget=budget or ScopeBudget(),
        command_runner=command_runner,
    )


# ---------------------------------------------- den ene regelen alt henger paa ---


def test_measured_blast_radius_wins_over_the_models_self_report(tmp_path: Path):
    """MUTASJONSMAALET.

    Modellen paastaar 1 fil / 2 linjer mens den faktisk skriver 2 filer og over
    tretti linjer. Fjern maalingen og bruk paastanden, og denne testen skal falle.

    Dette ER feilklassen kjeden er bygget for: et for stort tall som er skrevet ned
    som et lite, av en komponent som har alt aa tjene paa at det er lite.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    big = "\n".join(f"line_{i} = {i}" for i in range(40)) + "\n"
    patch = ProposedPatch(
        files={"a.py": big, "b.py": "y = 2\n"},
        model_claimed={"changed_files": 1, "changed_lines": 2},
        model_id="stub",
    )
    evidence = implementer(tmp_path, patch, lease=("a.py", "b.py")).build()

    assert evidence["changed_files"] == 2
    assert evidence["changed_lines"] > 30
    assert evidence["blast_radius_source"] == "measured:pre-image-diff"
    # Paastanden forsvinner ikke — den blir et funn.
    assert "changed_files: claimed 1, measured 2" in evidence["model_claimed_mismatch"]


def test_an_oversized_patch_reports_its_real_size_and_writes_nothing(tmp_path: Path):
    """Utfoereren krymper aldri sitt eget tall for aa slippe forbi sin egen vakt.

    Den enkleste maaten aa faa steg 8 til aa se vellykket ut paa, er aa rapportere
    et tall under grensen. Derfor maa nettopp den stien testes: for stor patch inn,
    ekte for store tall ut, og ingenting skrevet.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    huge = "\n".join(f"line_{i} = {i}" for i in range(60)) + "\n"
    impl = implementer(
        tmp_path,
        ProposedPatch(files={"a.py": huge}),
        budget=ScopeBudget(max_changed_lines=10),
    )
    with pytest.raises(ImplementationBlocked) as exc:
        impl.build()

    assert exc.value.gate == "scope_budget"
    assert exc.value.evidence["changed_lines"] > 10, "det ekte tallet skal ut, ikke et pyntet"
    assert "lines>10" in exc.value.evidence["scope_refusal"]
    assert "tests" not in exc.value.evidence, "ingenting ble kjoert, saa ingen testevidens"
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_the_runner_blocks_with_the_measured_number_in_the_reason(tmp_path: Path):
    """Atferdstest paa den haandhevede stien.

    Ikke bare AT den blokkerer, men at den ekte maalingen overlever inn i maalets
    `blocker` — det er den journalen laerer av. En blokkering som sier «no test
    evidence» om en patch som var for stor, har lagret feil aarsak.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    huge = "\n".join(f"line_{i} = {i}" for i in range(80)) + "\n"
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    runner = GovernedCodeRunner(scope_budget=ScopeBudget(max_changed_lines=5))
    impl = FaberImplementer.bound_to(
        runner,
        goal_id="g1",
        repo_root=tmp_path,
        lease_set=("a.py",),
        design=design_record(),
        design_store=DesignStore(tmp_path / "designs"),
        generator=StubGenerator(ProposedPatch(files={"a.py": huge})),
        command_runner=green_runner,
    )

    result = runner.run(
        FaberGoal("g1", "step 8", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-4050"),
        preflight=passing_preflight(),
        build=impl.build,
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, str(e["diff_id"]), "sol"),
        landing=lambda e: None,
    )
    assert result.goal.state is GoalState.BLOCKED
    assert "exceeds scope budget" in result.blocker
    assert "lines>5" in result.blocker
    assert "81 changed line" in result.blocker
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_bound_to_gives_the_implementer_the_runners_own_budget(tmp_path: Path):
    """To eksemplarer av en grense er to grenser som kan bli uenige.

    Er utfoererens slakkere, skriver den en patch runneren straks blokkerer — og
    treet staar skittent naar neste ticks steg 4 sjekker `git_clean`.
    """
    runner = GovernedCodeRunner(scope_budget=ScopeBudget(max_files=1))
    impl = FaberImplementer.bound_to(
        runner, goal_id="g1", repo_root=tmp_path, lease_set=("a.py",),
        design=design_record(), generator=StubGenerator(ProposedPatch(files={})),
    )
    assert impl.scope_budget is runner.scope_budget


def passing_preflight() -> PreflightResult:
    return PreflightResult(
        PreflightStatus.PASS,
        (),
        PreflightInput(
            git_clean=True,
            lease_clear=True,
            cad_status="verified",
            adr_status="accepted",
            bl_status="open",
            obsidian_status="fresh",
            source_refs={"git": "HEAD", "lease": "a.py", "cad": "CAD-M",
                         "adr": "ADR-062", "bl": "BL-4050"},
        ),
    )


# ------------------------------------------------- fravaer er ikke et funn ---


def test_an_empty_patch_is_BLOCKED_not_treated_as_a_small_change(tmp_path: Path):
    """Null filer er innenfor ethvert budsjett. Det er nettopp problemet.

    En tom patch ville passert vakten, faatt groenne tester paa uendret kode, og
    sett ut som et gjennomfoert steg 8. Det er stubben, med flere trinn.
    """
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, ProposedPatch(files={}, rationale="cannot be done")).build()
    assert "proposed no files" in str(exc.value)
    assert "cannot be done" in str(exc.value)


def test_a_patch_identical_to_the_current_files_is_BLOCKED(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, ProposedPatch(files={"a.py": "x = 1\n"})).build()
    assert "changed nothing" in str(exc.value)


def test_a_missing_step_7_design_is_BLOCKED(tmp_path: Path):
    impl = FaberImplementer(
        goal_id="ghost",
        repo_root=tmp_path,
        lease_set=("a.py",),
        design_store=DesignStore(tmp_path / "designs"),
        generator=StubGenerator(ProposedPatch(files={"a.py": "x = 2\n"})),
    )
    with pytest.raises(ImplementationBlocked) as exc:
        impl.build()
    assert exc.value.gate == "design_gate"


def test_a_design_that_names_no_test_is_BLOCKED(tmp_path: Path):
    store = DesignStore(tmp_path / "designs")
    store.save(DesignRecord(goal_id="g1", design="do a thing",
                            target_files=("a.py",), tests=()))
    with pytest.raises(ImplementationBlocked) as exc:
        store.load("g1")
    assert "tests" in str(exc.value)


def test_design_round_trips_through_the_store(tmp_path: Path):
    store = DesignStore(tmp_path / "designs")
    store.save(design_record())
    assert store.load("g1") == design_record()


# ----------------------------------------------------- leasen er grensen -----


def test_a_patch_outside_the_lease_writes_nothing(tmp_path: Path):
    """Steg 11 sammenligner strenger ved commit. Her finnes filsystemet, saa her
    stoppes skrivingen — foer den skjer, ikke etter."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": "x = 2\n", "andres_fil.py": "boom = 1\n"})
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, patch).build()
    assert "andres_fil.py" in str(exc.value)
    assert exc.value.gate == "landing_scope"
    assert not (tmp_path / "andres_fil.py").exists()
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_a_path_that_escapes_the_repo_is_BLOCKED(tmp_path: Path):
    """`../../etc/passwd` er inne i lease-settet som streng og utenfor repoet som
    fil. En streng-sjekk alene ser ikke forskjell."""
    escape = "sub/../../outside.py"
    impl = implementer(tmp_path, ProposedPatch(files={escape: "x = 1\n"}), lease=(escape,))
    with pytest.raises(ImplementationBlocked) as exc:
        impl.build()
    assert "escapes the repository" in str(exc.value)


# -------------------------------------------------- kvaliteten paa patchen ---


def test_python_that_does_not_parse_is_BLOCKED(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, ProposedPatch(files={"a.py": "def broken(\n"})).build()
    assert "not valid Python" in str(exc.value)
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_credential_shaped_content_is_BLOCKED(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": 'KEY = "sk-abcdefghijklmnopqrstuvwx"\n'})
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, patch).build()
    assert exc.value.gate == "security"


def test_ordinary_code_with_the_word_token_is_not_blocked(tmp_path: Path):
    """Falsk positiv her er ikke ufarlig: en gate som stopper alminnelig kode blir
    skrudd av, og en avskrudd gate er verre enn ingen."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": "def parse(token: str) -> str:\n    return token\n"})
    evidence = implementer(tmp_path, patch).build()
    assert evidence["tests"]


# ------------------------------------------------------ maaling og regnskap ---


def test_a_deletion_only_patch_is_not_measured_as_zero():
    """Med «bare tillegg» ville en ren sletting maalt 0 endrede linjer og passert et
    500-linjers budsjett som en null-endring. Churn-konvensjonen stenger den doera."""
    before = "\n".join(f"line {i}" for i in range(300)) + "\n"
    radius = measure_blast_radius({"a.py": before}, {"a.py": "line 0\n"})
    assert radius.deleted_lines == 299
    assert radius.changed_lines == 299
    assert radius.changed_files == 1


def test_a_new_file_counts_every_line_as_added():
    radius = measure_blast_radius({"new.py": None}, {"new.py": "a = 1\nb = 2\n"})
    assert (radius.added_lines, radius.deleted_lines, radius.changed_files) == (2, 0, 1)


def test_a_new_third_party_import_is_counted_as_a_dependency(tmp_path: Path):
    radius = measure_blast_radius(
        {"a.py": "x = 1\n"}, {"a.py": "import requests\nx = 1\n"}, repo_root=tmp_path
    )
    assert radius.new_dependencies == 1
    assert radius.dependencies == ("requests",)


def test_stdlib_and_first_party_imports_are_not_new_dependencies(tmp_path: Path):
    (tmp_path / "agent").mkdir()
    radius = measure_blast_radius(
        {"a.py": "x = 1\n"},
        {"a.py": "import json\nfrom agent.code_workflow import ScopeBudget\nx = 1\n"},
        repo_root=tmp_path,
    )
    assert radius.new_dependencies == 0


def test_a_new_dependency_blocks_the_default_budget(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": "import requests\nx = requests\n"})
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, patch).build()
    assert exc.value.evidence["new_dependencies"] == 1
    assert "dependencies>0" in exc.value.evidence["scope_refusal"]
    assert exc.value.evidence["new_dependency_names"] == "requests"


def test_diff_id_is_bound_to_the_bytes():
    """Er id-en et loepenummer, kan reviewerens id matche buildens selv om reviewer
    saa noe annet enn det som ble skrevet — og sammenligningen beviser ingenting."""
    assert diff_id_for({"a.py": "x = 1\n"}) == diff_id_for({"a.py": "x = 1\n"})
    assert diff_id_for({"a.py": "x = 1\n"}) != diff_id_for({"a.py": "x = 2\n"})
    assert diff_id_for({"a.py": "x = 1\n"}) != diff_id_for({"b.py": "x = 1\n"})


# ------------------------------------------------------------- testevidens ---


def test_failing_tests_produce_no_test_evidence_and_roll_the_tree_back(tmp_path: Path):
    """Runneren godtar en hvilken som helst ikke-tom `tests`-verdi, saa
    `"FAILED: 3"` herfra ville passert som testevidens. Derfor settes den ikke.

    Og aarsaken KASTES, av samme grunn som scope-avvisningen: en retur uten `tests`
    blokkeres paa «build returned no test evidence», og da har journalen lagret feil
    aarsak — neste tick proever igjen uten aa vite hvilken test som feilet.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(
            tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}), command_runner=red_runner
        ).build()

    assert exc.value.gate == "tests"
    assert "1 failed" in str(exc.value)
    assert "tests" not in exc.value.evidence
    assert "1 failed" in exc.value.evidence["test_failure"]
    assert exc.value.evidence["rolled_back"] == "a.py"
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_rollback_removes_a_file_that_did_not_exist_before(tmp_path: Path):
    impl = implementer(
        tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}), command_runner=red_runner
    )
    with pytest.raises(ImplementationBlocked):
        impl.build()
    assert not (tmp_path / "a.py").exists()


def test_a_green_build_writes_the_files_and_reports_its_own_size(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    evidence = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\ny = 3\n"})).build()

    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 2\ny = 3\n"
    assert evidence["tests"] == "1 passed in 0.01s"
    assert evidence["changed_files"] == 1
    assert evidence["written_files"] == "a.py"
    assert evidence["diff_id"].startswith("faber8-")


def test_the_runner_reaches_review_on_a_real_change(tmp_path: Path):
    """Ende-til-ende: steg 8 produserer noe, og kjeden kommer til reviewer-gaten
    paa evidens den ikke har skrevet selv."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}))
    seen: dict = {}

    result = GovernedCodeRunner().run(
        FaberGoal("g1", "step 8", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-4050"),
        preflight=passing_preflight(),
        build=impl.build,
        review=lambda e: seen.update(e) or ReviewEvidence(ReviewVerdict.BLOCK, str(e["diff_id"]), "sol"),
        landing=lambda e: None,
    )
    assert result.handoff is not None and result.handoff.required_gate == "reviewer"
    assert seen["diff_id"] == diff_id_for({"a.py": "x = 2\n"})
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 2\n"


# ------------------------------------------------------ generator-kontrakten ---


def test_the_envelope_is_parsed_strictly():
    patch = parse_patch_response(
        '```json\n{"files": [{"path": "a.py", "content": "x = 1\\n"}], "rationale": "why"}\n```'
    )
    assert patch.files == {"a.py": "x = 1\n"}
    assert patch.rationale == "why"


def test_prose_that_is_not_the_envelope_is_BLOCKED_not_mined_for_code():
    """Aa lete etter kodeblokker i fritekst ville produsert en patch av et svar som
    ikke var en patch — og den ville sett like ferdig ut som en ekte."""
    with pytest.raises(ImplementationBlocked):
        parse_patch_response("Sure! Here is the change:\n```python\nx = 1\n```")


def test_a_file_entry_without_content_is_BLOCKED():
    with pytest.raises(ImplementationBlocked):
        parse_patch_response('{"files": [{"path": "a.py"}]}')


def test_the_same_path_twice_is_BLOCKED():
    with pytest.raises(ImplementationBlocked) as exc:
        parse_patch_response(
            '{"files": [{"path": "a.py", "content": "1"}, {"path": "a.py", "content": "2"}]}'
        )
    assert "twice" in str(exc.value)


def test_a_model_supplied_count_is_captured_as_a_claim_not_as_evidence():
    patch = parse_patch_response(
        '{"files": [{"path": "a.py", "content": "x\\n"}], "changed_lines": 3}'
    )
    assert patch.model_claimed == {"changed_lines": 3}


def test_the_generator_sends_the_design_and_the_lease_to_cortex():
    sent: dict = {}

    def transport(url, payload, timeout):
        sent.update({"url": url, "payload": payload})
        return {"choices": [{"message": {"content": '{"files": [{"path": "a.py", "content": "x = 1\\n"}]}'}}]}

    generator = CortexPatchGenerator(base_url="http://cortex/v1", model="stub-model",
                                     transport=transport)
    patch = generator.generate(design_record(), {"a.py": "x = 0\n"}, budget=ScopeBudget())

    assert patch.files == {"a.py": "x = 1\n"}
    assert patch.model_id == "stub-model"
    assert sent["url"] == "http://cortex/v1/chat/completions"
    prompt = sent["payload"]["messages"][1]["content"]
    assert "add a greeting function" in prompt
    assert "- a.py" in prompt
    assert "tests/test_x.py" in prompt
    # Modellen skal vite at tallene maales, ikke oppgis.
    assert "measured from your output" in prompt


def test_a_cortex_response_without_a_message_is_BLOCKED():
    generator = CortexPatchGenerator(model="stub", transport=lambda u, p, t: {"choices": []})
    with pytest.raises(ImplementationBlocked) as exc:
        generator.generate(design_record(), {"a.py": None}, budget=ScopeBudget())
    assert exc.value.gate == "runtime"


def test_a_dead_cortex_is_BLOCKED_not_silently_skipped():
    def transport(url, payload, timeout):
        raise OSError("connection refused")

    generator = CortexPatchGenerator(model="stub", transport=transport)
    with pytest.raises(ImplementationBlocked) as exc:
        generator.generate(design_record(), {"a.py": None}, budget=ScopeBudget())
    assert "cortex call failed" in str(exc.value)


# ------------------------------------------------------------- atomisitet ----


def test_a_write_that_fails_midway_leaves_the_tree_as_it_was(tmp_path: Path, monkeypatch):
    """Halvparten av en endring bestaar ingen test og beskrives av ingen review."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    impl = implementer(
        tmp_path,
        ProposedPatch(files={"a.py": "x = 2\n", "b.py": "y = 2\n"}),
        lease=("a.py", "b.py"),
    )
    impl.read_pre_images()

    real_resolve = impl.resolve

    def explode(path: str):
        if path == "b.py":
            raise OSError("disk full")
        return real_resolve(path)

    monkeypatch.setattr(impl, "resolve", explode)
    with pytest.raises(OSError):
        impl.write({"a.py": "x = 2\n", "b.py": "y = 2\n"})

    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "y = 1\n"


# ------------------------------ BL-4050 reviewer-runde 1: de seks funnene ----


def test_a_credential_in_the_evidence_rolls_the_tree_back_before_blocking(tmp_path: Path):
    """FUNN 1. Sikkerhetsjekken laa ETTER skrivingen og kastet uten opprydning.

    En `PermissionError` ut av `build()` uten tilbakerulling etterlater treet
    skittent — og det er tilstanden modulens egen docstring sier en autonom loop
    ikke kommer ut av: neste ticks steg 4 feiler paa vaart eget rot.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    class Sneaky(dict):
        """Evidens som slipper unna redigeringen og trigger bakstopperen."""

    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}))
    original = impl._safe_evidence

    def poisoned(evidence):
        return original({**dict(evidence), "note": {"api_key": "hunter2"}})

    impl._safe_evidence = poisoned
    with pytest.raises(ImplementationBlocked) as exc:
        impl.build()

    assert exc.value.gate == "security"
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n", "treet maa vaere rullet tilbake"


def test_a_credential_in_the_model_rationale_is_redacted_not_fatal(tmp_path: Path):
    """En verifisert, groenn build skal ikke kastes fordi modellen skrev
    «api_key=» i prosaen sin. Fritekst REDIGERES; filinnhold BLOKKERES."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    patch = ProposedPatch(
        files={"a.py": "x = 2\n"},
        rationale="the caller passes api_key=sk-livekey-not-a-placeholder instead",
    )
    evidence = implementer(tmp_path, patch).build()
    assert evidence["tests"]
    assert "sk-livekey" not in evidence["rationale"]
    assert "redacted" in evidence["rationale"]


def test_a_file_that_moved_under_us_during_the_cortex_call_is_not_clobbered(tmp_path: Path):
    """FUNN 2. Mellom lesingen og skrivingen ligger et kall som kan ta minutter,
    og lease-eieren er per PRINSIPAL, ikke per kjoering — to samtidige Faber-
    kjoeringer blokkerer ikke hverandre. Uten sjekken bakser vi bort den andres
    arbeid uten aa se det."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}))
    impl.read_pre_images()
    (tmp_path / "a.py").write_text("parallel = True\n", encoding="utf-8")

    with pytest.raises(ImplementationBlocked) as exc:
        impl.write({"a.py": "x = 2\n"})

    assert exc.value.gate == "lease"
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "parallel = True\n"


def test_rollback_never_overwrites_someone_elses_later_edit(tmp_path: Path):
    """En tilbakerulling som skriver pre-imaget tilbake ubetinget er en NY
    overskriving — opprydningen ville vaert skaden den skulle rydde opp etter."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}))
    impl.read_pre_images()
    impl.write({"a.py": "x = 2\n"})
    (tmp_path / "a.py").write_text("someone_else = True\n", encoding="utf-8")

    assert impl.rollback() == ()
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "someone_else = True\n"


def test_a_flag_as_a_test_target_is_BLOCKED(tmp_path: Path):
    """FUNN 3. `pytest -q --collect-only` avslutter med 0 uten aa kjoere noe.
    Groenn uten aa ha kjoert er verre enn roed."""
    design = DesignRecord(goal_id="g1", design="d", target_files=("a.py",),
                          tests=("--collect-only",))
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}), design=design)
    with pytest.raises(ImplementationBlocked) as exc:
        impl.build()
    assert exc.value.gate == "design_gate"
    assert "flag" in str(exc.value)
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_a_test_path_that_does_not_exist_is_BLOCKED(tmp_path: Path):
    design = DesignRecord(goal_id="g1", design="d", target_files=("a.py",),
                          tests=("tests/test_imaginary.py::test_it",))
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}), design=design)
    with pytest.raises(ImplementationBlocked) as exc:
        impl.build()
    assert "does not exist" in str(exc.value)


def test_a_broken_resolver_import_is_translated_not_raw(tmp_path: Path, monkeypatch):
    """FUNN 5. Importen laa over try-blokken som finnes for aa oversette nettopp
    denne feilen, saa en ImportError slapp raa forbi den ene oversetteren."""
    import builtins

    real_import = builtins.__import__

    def blow_up(name, *args, **kwargs):
        if name == "agent.continuous_pipeline":
            raise ImportError("no continuous_pipeline in this tree")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blow_up)
    with pytest.raises(ImplementationBlocked) as exc:
        CortexPatchGenerator().resolve_model()
    assert exc.value.gate == "runtime"


def test_a_credential_in_a_refusal_reason_never_reaches_the_goal_blocker(tmp_path: Path):
    """FUNN 1b, og den som faktisk persisteres.

    Runnerens ytre haandterer beholder BARE `str(exc)` — `evidence` og `gate`
    forkastes. Vakten laa altsaa paa kanalen som blir kastet, mens den som havner i
    maalets `blocker` og i journalen sto uten.

    Derfor gaar denne testen gjennom runneren og leser `goal.blocker`. En
    `pytest.raises` paa klassenivaa ville passert mens lekkasjen fortsatt landet i
    journalen — nettopp det den forrige testrunden gjorde.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    leak = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
    impl = implementer(
        tmp_path,
        ProposedPatch(files={}, rationale=f"gave up, {leak} rejected"),
    )

    result = GovernedCodeRunner().run(
        FaberGoal("g1", "step 8", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-4050"),
        preflight=passing_preflight(),
        build=impl.build,
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        landing=lambda e: None,
    )
    assert result.goal.state is GoalState.BLOCKED
    assert leak not in result.goal.blocker
    assert leak not in result.blocker
    assert "redacted" in result.goal.blocker


def test_a_credential_in_a_filename_is_redacted_too(tmp_path: Path):
    """Modellen styrer filnavnene den foreslaar, ikke bare begrunnelsen."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    leak = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
    with pytest.raises(ImplementationBlocked) as exc:
        implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n",
                                                   f"leak_{leak}.py": "y = 1\n"})).build()
    assert leak not in str(exc.value)


def test_redaction_keeps_the_reason_and_removes_only_the_secret(tmp_path: Path):
    """Reviewer-runde 3: en trygg blocker som ikke sier NOE er ikke trygg nok.

    Foerste versjon byttet ut hele strengen, og maalt paa realistisk avvisningsprosa
    var det 5 av 5 falske positive. Da runneren i tillegg forkaster `gate`, satt
    maalet igjen med en blocker uten ett handlingsbart ord — BL-4029-defekten
    («journalen lagret feil aarsak») gjeninnfoert av rettelsen for en annen.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    impl = implementer(
        tmp_path,
        ProposedPatch(files={}, rationale=(
            "the design needs api_key=sk-ABCDEFGHIJKLMNOPQRSTUVWX wired through, "
            "but config.py is not in the lease")),
    )

    result = GovernedCodeRunner().run(
        FaberGoal("g1", "step 8", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-4050"),
        preflight=passing_preflight(),
        build=impl.build,
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        landing=lambda e: None,
    )
    blocker = result.goal.blocker
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX" not in blocker
    assert "redacted" in blocker
    # ...og resten av setningen maa fortsatt kunne handles paa:
    assert "proposed no files" in blocker, "gaten maa fortsatt vaere lesbar"
    assert "config.py is not in the lease" in blocker, "begrunnelsen maa overleve"


def test_ordinary_refusal_prose_is_not_wiped(tmp_path: Path):
    """Prosa som bare NEVNER auth-kode er ikke en lekkasje, og skal ikke koste
    hele begrunnelsen."""
    assert _redact("cannot implement: the helper reads password: str from settings") \
        .endswith("from settings")
    assert "cannot implement" in _redact(
        "cannot implement: the helper reads password: str from settings")


def test_a_private_key_block_is_removed_whole_not_just_its_header(tmp_path: Path):
    """Reviewer-runde 4: detektoren og redigereren var uenige om hva funnet BESTOD i.

    Hode-moensteret oppdaget noekkelen korrekt — og span-erstatningen fjernet saa
    bare ordet «BEGIN...KEY», slik at selve noekkelmaterialet ble staaende igjen i
    `goal.blocker`. Helstreng-varianten hadde ikke det hullet; span-varianten
    innfoerte det.

    Markoeren bygges av deler her med vilje: en literal PEM-header i en committet
    testfil ville trippet repoets egne hemmelighets-skannere uten aa teste noe mer.
    """
    header = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
    footer = "-----END " + "RSA PRIVATE KEY" + "-----"
    body = "MIIEowIBAAKCAQEAfake0000notarealkey0000fake0000notarealkey0000"
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    impl = implementer(
        tmp_path,
        ProposedPatch(files={}, rationale=(
            f"cannot proceed, the fixture embeds:\n{header}\n{body}\n{footer}\n"
            "which is not in the lease")),
    )

    result = GovernedCodeRunner().run(
        FaberGoal("g1", "step 8", cad_ref="CAD-M", adr_ref="ADR-062", bl_ref="BL-4050"),
        preflight=passing_preflight(),
        build=impl.build,
        review=lambda e: ReviewEvidence(ReviewVerdict.PASS, "d", "sol"),
        landing=lambda e: None,
    )
    assert body not in result.goal.blocker, "noekkelmaterialet maa vaere borte, ikke bare hodet"
    assert header not in result.goal.blocker
    assert "which is not in the lease" in result.goal.blocker, "begrunnelsen maa overleve"


def test_an_unterminated_private_key_is_still_detected():
    """`|$`-alternativet: uten det slutter en AVKORTET noekkel aa bli oppdaget i det
    hele tatt — en daarligere byttehandel enn den var ment aa loese."""
    header = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
    body = "MIIEowIBAAKCAQEAfake0000notarealkey0000"
    out = _redact(f"embeds:\n{header}\n{body}")
    assert body not in out
    assert "embeds:" in out


def test_rollback_skipped_does_not_leak_across_builds_on_one_instance(tmp_path: Path):
    """Reviewer-runde 4: denne mutanten OVERLEVDE — rettelsen var riktig plassert,
    men ingenting testet den."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"}))
    impl.read_pre_images()
    impl.write({"a.py": "x = 2\n"})
    (tmp_path / "a.py").write_text("someone_else = True\n", encoding="utf-8")
    impl.rollback()
    assert impl._skipped_rollback == ["a.py"]

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    evidence = impl.build()
    assert impl._skipped_rollback == [], "stale sti fra forrige build maa vaere nullstilt"
    assert "rollback_skipped" not in evidence


# ------------------------------------------ BL-4055 F1: diffen steg 10b leser ---


def test_build_emits_the_diff_the_second_opinion_reviews(tmp_path: Path):
    """Uten dette feltet er andre-meningen en VEGG, ikke en gate.

    Reviewer maalte det: ingen produksjonssti satte ``evidence["diff"]``, saa hver
    utloest endring paa ``faber_runtime --tick-json`` endte i
    ``second_opinion_input`` -- deterministisk, av en grunn som ikke hadde noe med
    endringen aa gjoere, med et next_step ingen operatoer kunne handle paa.

    Vakten sjekker INNHOLD, ikke bare at noekkelen finnes: en tom streng ville
    utloest noeyaktig samme blokkering.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": "x = 2\ny = 3\n"}, rationale="bump")
    evidence = implementer(tmp_path, patch).build()

    assert evidence["diff"].strip(), "step 8 produced no diff for step 10b to review"
    assert "-x = 1" in evidence["diff"]
    assert "+x = 2" in evidence["diff"]
    assert "b/a.py" in evidence["diff"]


def test_the_reviewed_diff_is_redacted_before_it_leaves_the_process():
    """Diffen er en NY EGRESS: filinnhold gaar til api.anthropic.com.

    `vet()` er FOERSTE linje og avviser en patch med kreditiv-formet materiale
    foer `build` i det hele tatt naar evidensen -- saa denne stien kan normalt
    ikke naas gjennom en patch. Redigeringen i `render_review_diff` er derfor
    DYBDEFORSVAR, og testes direkte paa rendereren: den skal holde ogsaa for
    innhold som ikke kom gjennom `vet` (et pre-image som allerede laa i treet,
    for eksempel), fordi det er det som faktisk sendes ut av prosessen.
    """
    from agent.faber_implementer import render_review_diff

    rendered = render_review_diff(
        {"a.py": 'api_key = "sk-ant-not-a-real-key-000"\n'},
        {"a.py": "api_key = os.environ['K']\n"})

    assert "sk-ant-not-a-real-key-000" not in rendered
    assert rendered.strip(), "redaction must not empty the diff — the change is still reviewable"


def test_an_unchanged_file_contributes_nothing_to_the_reviewed_diff(tmp_path: Path):
    """Diffen skal vise ENDRINGEN, ikke hele leasen.

    En diff full av uendrede filer bruker vurdererens kontekstvindu paa stoey og
    gjoer det vanskeligere aa se det som faktisk skjedde.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("keep = True\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": "x = 2\n", "b.py": "keep = True\n"},
                          rationale="only a")
    evidence = implementer(tmp_path, patch, lease=("a.py", "b.py")).build()

    assert "a/a.py" in evidence["diff"]
    assert "b.py" not in evidence["diff"]


def test_the_reviewed_diff_is_built_from_the_same_images_as_the_diff_id(tmp_path: Path):
    """Samme kilde som ``diff_id_for`` og ``measure_blast_radius``.

    Hadde teksten kommet fra en annen kilde -- ``git diff`` mot arbeidstreet, for
    eksempel -- kunne reviewerens ``diff_id`` matche buildens mens teksten viste
    noe annet, og da beviser sammenligningen paa steg 10 ingenting.
    """
    from agent.faber_implementer import diff_id_for, render_review_diff

    pre = {"a.py": "x = 1\n"}
    post = {"a.py": "x = 2\n"}
    rendered = render_review_diff(pre, post)
    assert "+x = 2" in rendered
    # Samme post-sett -> samme identitet; diffen beskriver akkurat det settet.
    assert diff_id_for(post) == diff_id_for({"a.py": "x = 2\n"})
    assert render_review_diff(post, post) == "", "no change means no diff to review"


def test_ordinary_source_does_not_block_step_8_on_security(tmp_path: Path):
    """BL-4055 F5. DEN vanligste falske positiven i ekte kildekode.

    `model_api_key = ""` matcher IKKE noekkelord-moensteret raatt -- en tom streng
    er ingen hemmelighet. Men `_safe_evidence` avsluttet med
    `assert_safe(json.dumps(payload))`, og JSON-escaping skriver den om til
    `model_api_key = \\"\\"`: da leverer ESCAPE-TEGNET den ikke-tomme verdien
    kilden ikke hadde, og buildet blokkerte paa `gate=security` med tilbakerulling.

    Reviewer maalte 12 slike filer i repoet. Verre: `_safe_evidence(evidence)`
    evalueres som ARGUMENT til `ImplementationBlocked` paa scope-stien, saa den
    falske sikkerhets-feilen kastet FOERST og skjulte den ekte aarsaken -- BL-4029s
    «journalen lagret feil aarsak», gjeninnfoert av en rettelse for noe annet.
    """
    (tmp_path / "a.py").write_text(
        'model_api_key = ""\nvalue = model_api_key or "K"\n', encoding="utf-8")
    patch = ProposedPatch(
        files={"a.py": 'model_api_key = ""\nvalue = model_api_key or "KEY2"\n'},
        rationale="rename the fallback")

    evidence = implementer(tmp_path, patch).build()

    assert evidence["diff"].strip()
    assert "KEY2" in evidence["diff"], "legitimate source must survive intact"


def test_keyword_shaped_but_legitimate_code_is_not_redacted(tmp_path: Path):
    """Noekkelord-moenstre hoerer ikke hjemme paa filinnhold.

    `api_key = os.environ[...]` er RIKTIG kode -- det er maaten aa gjoere det paa.
    Foerste versjon kjoerte full `SecretPolicy` paa diffen og sproeytet `(redacted)`
    inn i 146 av 558 ekte filer. Verst der gaten sikter: en endring i
    `hermes_cli/auth.py` naadde vurdereren med de relevante linjene blanket ut, og
    da er DISSENT den korrekte oppfoerselen -- gaten ble daarligst akkurat paa
    governance-flaten den ble bygget for.
    """
    (tmp_path / "a.py").write_text("api_key = os.environ['K']\n", encoding="utf-8")
    patch = ProposedPatch(files={"a.py": "api_key = os.environ['KEY2']\n"},
                          rationale="rename env var")

    evidence = implementer(tmp_path, patch).build()

    assert "(redacted)" not in evidence["diff"]
    assert "os.environ['KEY2']" in evidence["diff"]


def test_a_real_provider_key_in_a_pre_image_is_still_redacted(tmp_path: Path):
    """Dybdeforsvaret staar: FORMENE redigeres fortsatt.

    `vet()` avviser en PATCH med kreditiv-formet materiale, men den saa aldri
    pre-imaget. En ekte noekkel som alt laa i treet skal ikke reise ut av prosessen
    til api.anthropic.com bare fordi linjen rundt den ble endret.
    """
    from agent.faber_implementer import render_review_diff

    rendered = render_review_diff(
        {"a.py": 'KEY = "sk-antxxxxxxxxxxxxxxxxxxxxxxxx"\n'},
        {"a.py": "KEY = os.environ['K']\n"})

    assert "sk-antxxxxxxxxxxxxxxxxxxxxxxxx" not in rendered
    assert "(redacted)" in rendered


def test_the_diff_backstop_fires_when_a_producer_bypasses_the_renderer(tmp_path: Path):
    """M3: bakstoppen var udekket, og reviewer slettet den uten at noe feilet.

    Den er INERT-VED-KONSTRUKSJON for alt som gaar gjennom `render_review_diff`
    (reviewer beviste det med 4008 fuzz-input og null treff), saa den kan bare
    voktes ved aa gjoere det den finnes for: sette `evidence["diff"]` UTENOM
    rendereren. Da er den den eneste kontrollen mellom filinnholdet og
    api.anthropic.com.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"},
                                               rationale="bump"))

    with pytest.raises(ImplementationBlocked) as exc:
        impl._safe_evidence({
            "tests": "ok",
            # Uredigert, som en framtidig produsent kunne finne paa aa levere.
            "diff": '+KEY = "sk-antxxxxxxxxxxxxxxxxxxxxxxxx"\n',
        })

    assert exc.value.gate == "security"
    assert "credential-shaped" in str(exc.value)


def test_the_reviewed_diff_carries_more_context_than_difflib_default(tmp_path: Path):
    """M6: `n=10` var begrunnet i en docstring, men holdt av ingenting.

    Begrunnelsen er at vurdereren blir bedt om aa finne «en kontroll som ikke kan
    fyre» -- det ser man ikke av tre linjer. Et ubundet tall i en docstring som
    forklarer hvorfor det betyr noe, er hvordan de tre forrige funnene startet.
    """
    from agent.faber_implementer import render_review_diff

    body = "".join(f"line_{i} = {i}\n" for i in range(40))
    changed = body.replace("line_20 = 20", "line_20 = 999")
    rendered = render_review_diff({"a.py": body}, {"a.py": changed})

    context = [ln for ln in rendered.splitlines()
               if ln.startswith(" ") and "line_" in ln]
    assert len(context) >= 14, (
        f"only {len(context)} context lines — difflib's default of 3 gives 6; "
        "the reviewer cannot see a control that cannot fire from that")


# ------------------------------------ BL-4055 F7: literal-regelen var uvoktet ---
#
# Reviewer: tre mutanter overlevde, fordi INGEN test roerte `_LITERAL_SECRET`.
# Shape-halvdelen var voktet av `sk-`-testen; literal-halvdelen av ingenting.


def test_a_literal_secret_in_a_pre_image_is_masked_but_the_keyword_survives():
    """Bare VERDIEN maskeres. Leseren skal fortsatt se AT det er en hemmelighet."""
    from agent.faber_implementer import render_review_diff

    rendered = render_review_diff(
        {"a.py": 'password = "hunter2-prod-db-password"\n'},
        {"a.py": "password = os.environ['DB_PW']\n"})

    assert "hunter2-prod-db-password" not in rendered
    assert "password" in rendered, "the keyword must survive; only the value goes"
    assert "(redacted)" in rendered


def test_a_full_authorization_header_literal_is_masked():
    """F6: header-navn og verdi i ÉN literal.

    Dette var det ene stedet den smale literal-regelen REGREDERTE mot de fulle
    noekkelord-moenstrene den erstattet -- og det er hvordan en header-konstant
    faktisk skrives.
    """
    from agent.faber_implementer import render_review_diff

    rendered = render_review_diff(
        {"a.py": 'AUTH_HEADER = "Authorization: Basic dXNlcjpwYXNzd29yZA=="\n'},
        {"a.py": "AUTH_HEADER = build_auth()\n"})

    assert "dXNlcjpwYXNzd29yZA==" not in rendered
    assert "(redacted)" in rendered


def test_a_bare_authorization_mention_is_not_redacted():
    """Skjema-moensteret krever ET SKJEMA, ikke bare ordet.

    Uten dette ville hver docstring som naevner headeren blitt maskert -- og det
    er den falske-positiv-klassen hele F5 handlet om.
    """
    from agent.faber_implementer import render_review_diff

    line = "# See the Authorization header documentation for details\n"
    rendered = render_review_diff({"a.py": line}, {"a.py": line + "x = 1\n"})

    assert "(redacted)" not in rendered


def test_the_literal_rule_never_spans_a_line_boundary():
    """DEN vakten som manglet mest -- mutanten som gjeninnfoerer min egen bug.

    Foerste versjon av verdiklassen var ``[^"']{16,}``, som tillater LINJESKIFT.
    Den spente seg fra én strengliteral, over ekte kode, til den neste og maskerte
    alt imellom -- maalt 3 slike, alle i ``print()``-kall. Det er «blank ut
    legitim logikk»-feilen i miniatyr, innfoert av rettelsen FOR den.
    """
    from agent.faber_implementer import render_review_diff

    body = ('print("Password: ")\n'
            "confirm = compute_the_thing(a, b)\n"
            'print("Enter it again: ")\n')
    rendered = render_review_diff({"a.py": body}, {"a.py": body + "x = 1\n"})

    assert "compute_the_thing(a, b)" in rendered, (
        "a newline-spanning match blanked legitimate code between two literals")


def test_two_secrets_on_separate_lines_leave_the_code_between_them_intact():
    from agent.faber_implementer import render_review_diff

    body = ('api_key = "aaaaaaaaaaaaaaaaaaaaaaaa"\n'
            "result = do_real_work(x)\n"
            'token = "bbbbbbbbbbbbbbbbbbbbbbbb"\n')
    rendered = render_review_diff({"a.py": body}, {"a.py": body + "x = 1\n"})

    assert rendered.count("(redacted)") == 2
    assert "do_real_work(x)" in rendered
    assert "aaaaaaaaaaaaaaaaaaaaaaaa" not in rendered
    assert "bbbbbbbbbbbbbbbbbbbbbbbb" not in rendered


def test_the_backstop_also_covers_the_literal_rule(tmp_path: Path):
    """M3b: bakstoppen mistet literal-regelen uten at noe feilet."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    impl = implementer(tmp_path, ProposedPatch(files={"a.py": "x = 2\n"},
                                               rationale="bump"))

    with pytest.raises(ImplementationBlocked) as exc:
        impl._safe_evidence({
            "tests": "ok",
            "diff": '+password = "hunter2-prod-db-password"\n',
        })

    assert exc.value.gate == "security"

    # N4: og skjema-moensteret. Den ble lagt til i bakstoppen uten en test, saa
    # aa fjerne den igjen kostet ingenting -- samme hull som literal-regelen
    # hadde. Hver kontroll i `_file_content_violations` trenger sin egen linje.
    with pytest.raises(ImplementationBlocked) as exc2:
        impl._safe_evidence({
            "tests": "ok",
            "diff": '+H = "Authorization: Bearer abcdefghijklmnopqrst"\n',
        })

    assert exc2.value.gate == "security"


def test_redaction_is_a_fixed_point_of_the_backstop():
    """DEN baerende invarianten mellom de to kontrollene.

    `_redact_file_content` maa produsere noe `_file_content_violations` sier er
    rent. Ellers blokkerer bakstoppen paa redigeringens EGET resultat, og steg 8
    doer paa `gate=security` for en endring uten hemmeligheter i seg.

    MAALT to ganger, begge ganger som en regresjon:
      * F5: `_redact` skannet raatekst mens bakstoppen skannet den JSON-escapede
        formen, saa `model_api_key = ""` blokkerte 12 ekte filer.
      * F6: `_AUTH_SCHEME` matchet sin egen markoer -- ``(redacted)`` er ti tegn
        uten mellomrom, saa ``\\S{8,}`` traff den. Blokkeringene gikk 0 -> 10 i
        samme sekund moensteret ble lagt inn.

    Begge ganger var koden «aapenbart riktig» og begge ganger var det maalingen
    som avslo. Denne testen er den maalingen, gjort permanent.
    """
    from agent.faber_implementer import (_file_content_violations,
                                         _redact_file_content)

    corpus = [
        'KEY = "sk-antxxxxxxxxxxxxxxxxxxxxxxxx"',
        'password = "hunter2-prod-db-password"',
        'AUTH_HEADER = "Authorization: Basic dXNlcjpwYXNzd29yZA=="',
        'H = "Authorization: Bearer abcdefghijklmnopqrstuvwx"',
        'ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        "AKIA0123456789ABCDEF",
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----\ntruncated",       # `|$`-grenen
        'api_key = os.environ["K"]',                          # legitim
        "# see the Authorization header docs",                # legitim
        "",
    ]
    # Enkeltvis, parvis og dobbelt -- en markoer som selv blir et treff dukker
    # typisk opp foerst naar to moenstre moetes.
    cases = list(corpus)
    cases += [a + "\n" + b for a in corpus for b in corpus]
    cases += [a + a for a in corpus]

    for case in cases:
        cleaned = _redact_file_content(case)
        assert not _file_content_violations(cleaned), (
            "redaction is not a fixed point of the backstop — the backstop would "
            f"block on its own output for: {case[:60]!r}")
        # Idempotent: aa redigere en gang til skal ikke endre noe.
        assert _redact_file_content(cleaned) == cleaned


def test_masking_an_auth_header_keeps_the_string_terminator():
    """N1: `\\S{8,}` var hoeyre-ubundet og spiste avslutningstegnet.

        h = f"Authorization: Bearer {self.access_token}"
      ->  h = f"Authorization: Bearer (redacted)          <- uterminert

    Vurdereren fikk en oedelagt literal aa lese, i en auth-modul -- altsaa
    noeyaktig der gaten sikter. Samme familie som spennet over linjeskift.

    Og bindingen kunne ikke gjoeres alene: med anfoerselstegnet i behold matchet
    literal-regelen ``"Bearer (redacted)"`` (17 tegn) paa neste skanning, saa
    bakstoppen fyrte paa sitt eget resultat. Fikspunktet holdt BARE fordi mangelen
    spiste tegnet. Begge moenstrene er derfor markoer-immune naa.
    """
    from agent.faber_implementer import render_review_diff

    line = 'h = f"Authorization: Bearer {self.access_token}"'
    rendered = render_review_diff({"a.py": line + "\n"}, {"a.py": line + "\n# x\n"})

    masked = [ln for ln in rendered.splitlines() if "Authorization" in ln][0]
    assert masked.rstrip().endswith('"'), (
        f"the closing quote was swallowed: {masked!r}")
    assert "(redacted)" in masked
