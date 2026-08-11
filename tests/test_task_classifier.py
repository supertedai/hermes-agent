# BL-4056 — tester for steg 3-klassifisereren.
"""Testene er skrevet rundt to spørsmål, ikke rundt metodene.

1. **Finnes det en sekvens av legitime handlinger som gir BL?**  Det er
   falsifikatoren ``PreflightGate`` ikke hadde svar på i 340 samples
   (ADR-062 §5). En klassifiserer som alltid sier ADR er like ubrukelig som
   en som alltid sier BL — bare dyrere.

2. **Kan noen komme seg NED i den billige klassen?**  Hver test som handler
   om nedgradering er en test på skjevheten modulen finnes for.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from agent.code_workflow import ScopeBudget
from agent.task_classifier import (
    ADR_ALLOCATOR_CMD,
    Classification,
    DesignReviewRequest,
    Disposition,
    MeasuredScope,
    Reversibility,
    Signal,
    TaskClass,
    TaskClassifier,
    TaskProposal,
    UnavailableReviewer,
    assert_independent_reviewer,
    parse_adr_ref,
    parse_contract_ref,
)


def clean_bl_proposal(**over) -> TaskProposal:
    """En ærlig BL: reversibel, navngitt kontrakt, begge grenser besvart.

    Alt her er noe en ekte proposer faktisk kan svare på steg 3 — ingenting
    krever et artefakt kjeden produserer senere.
    """
    base = dict(
        title="Rett feilmelding i kanban-dispatch-låsen",
        description=(
            "Låsen logger «locked» uten å si hvem som holder den. Legg til "
            "holder-id i meldingen. Ingen endring i låsens oppførsel."
        ),
        touched_paths=("hermes_cli/kanban_db.py",),
        reversibility=Reversibility.REVERSIBLE,
        contract_ref="hermes_cli.kanban_db.dispatch_lock (eksisterende)",
        declared_trust_boundary_change=False,
        declared_new_register=False,
        estimated_changed_files=1,
        estimated_changed_lines=8,
    )
    base.update(over)
    return TaskProposal(**base)


# ---------------------------------------------------------------------------
# 1. Falsifikatoren: BL MÅ være nåbar.
# ---------------------------------------------------------------------------

def test_a_legitimate_sequence_of_actions_actually_reaches_BL():
    """Uten denne er modulen bare ``PreflightGate`` på nytt, i ny drakt."""
    result = TaskClassifier().classify(clean_bl_proposal())
    assert result.task_class is TaskClass.BL
    assert result.design_review_required is False
    assert result.requires_adr_allocation is False
    assert "steg 4" in result.next_action


# ---------------------------------------------------------------------------
# 2. De fire ADR-signalene Morten navnga.
# ---------------------------------------------------------------------------

def test_trust_boundary_in_the_wording_is_ADR():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Gi kjeden lov til å lande uten godkjenning",
        declared_trust_boundary_change=True,
    ))
    assert result.task_class is TaskClass.ADR
    assert any(h.signal is Signal.TRUST_BOUNDARY for h in result.hits)


def test_the_ADR_062_V5_sentence_classifies_as_ADR():
    """Regresjonstesten mot presedensen.

    Setningen står hardkodet i ``faber_control_bridge.run_all`` fordi et
    menneske skrev den. Klassifisereren skal komme fram til det samme uten at
    noen hardkoder svaret.
    """
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Gi dry_run_13_step landingsevne",
        description=(
            "Aa gi denne stien landingsevne er en autonomi-grense-endring "
            "(ADR-062 V5) og hard-limit #3."
        ),
        declared_trust_boundary_change=True,
    ))
    assert result.task_class is TaskClass.ADR
    signals = {h.signal for h in result.hits}
    assert Signal.TRUST_BOUNDARY in signals
    assert Signal.HARD_LIMIT in signals


def test_hard_limit_path_is_ADR_even_when_the_wording_is_innocent():
    """Stien er målt. En uskyldig tittel overprøver den ikke."""
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Rydd i konfigfil",
        description="Fjerner et ubrukt felt.",
        touched_paths=("/etc/ssh/sshd_config",),
    ))
    assert result.task_class is TaskClass.ADR
    hit = next(h for h in result.hits if h.signal is Signal.HARD_LIMIT)
    assert hit.source == "measured"
    assert "sshd_config" in hit.evidence


def test_destructive_graph_mutation_in_the_diff_is_ADR():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Rydd i foreldede noder",
        description="Fjerner noder ingen bruker.",
        diff_text="MATCH (n:Stale) DETACH DELETE n",
    ))
    assert result.task_class is TaskClass.ADR
    assert any("hard-limit #4" in h.evidence for h in result.hits)


def test_a_new_allocator_is_a_new_namespace_and_therefore_ADR():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Legg til nummerutdeling for oppgaver",
        description="En liten teller.",
        diff_text="def allocate_task_number(...):\n    ...",
        declared_new_register=True,
    ))
    assert result.task_class is TaskClass.ADR
    assert any(h.signal is Signal.NEW_REGISTER for h in result.hits)


def test_cross_surface_contract_is_ADR():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Ny integrasjon mellom Hermes og AGI-grafen",
        description="Eksponer et endepunkt.",
        declared_new_register=True,
    ))
    assert result.task_class is TaskClass.ADR


# ---------------------------------------------------------------------------
# 3. Tvil er en klasse, ikke en avrunding.
# ---------------------------------------------------------------------------

def test_unknown_reversibility_is_DOUBT_not_BL():
    result = TaskClassifier().classify(
        clean_bl_proposal(reversibility=Reversibility.UNKNOWN))
    assert result.task_class is TaskClass.DOUBT
    assert any(h.signal is Signal.UNKNOWN_REVERSIBILITY for h in result.hits)
    assert "IKKE bygg" in result.next_action


def test_missing_contract_ref_is_DOUBT_not_BL():
    result = TaskClassifier().classify(clean_bl_proposal(contract_ref="   "))
    assert result.task_class is TaskClass.DOUBT
    assert any(h.signal is Signal.MISSING_CONTRACT_REF for h in result.hits)


@pytest.mark.parametrize("field_name", [
    "declared_trust_boundary_change",
    "declared_new_register",
])
def test_an_unanswered_boundary_question_is_DOUBT_not_a_no(field_name):
    """``None`` er «ingen svarte», ikke «nei».

    Å la ubesvart bety ``False`` ville delt ut den billige klassen gratis til
    den som lot være å svare.
    """
    result = TaskClassifier().classify(clean_bl_proposal(**{field_name: None}))
    assert result.task_class is TaskClass.DOUBT
    assert any(h.signal is Signal.UNDECLARED_BOUNDARY for h in result.hits)


def test_an_empty_title_is_DOUBT_because_empty_is_not_small():
    result = TaskClassifier().classify(clean_bl_proposal(title="   ", description=""))
    assert result.task_class is TaskClass.DOUBT
    assert any(h.signal is Signal.EMPTY_PROPOSAL for h in result.hits)


# --- reviewer-funn B1: et ærlig ja må koste minst like mye som å tie -------

def test_an_honest_yes_is_itself_an_ADR_signal():
    """REVIEWER-FUNN. Uten dette ga et sant «ja» null treff, altså BL."""
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Utvid Faber med steg 13",
        description="steg 13 landing",
        declared_trust_boundary_change=True,
        declared_new_register=True,
    ))
    assert result.task_class is TaskClass.ADR
    declared = [h for h in result.hits if h.source == "declared"
                and h.disposition is Disposition.ADR]
    assert declared, "en erklært grenseflytting skal være et signal i seg selv"


def test_answering_truthfully_is_never_cheaper_than_refusing_to_answer():
    """Skjevheten reviewer fant: sant «ja» -> BL, ubesvart -> DOUBT.

    Å svare sant var strengt billigere enn å la være. Det er den samme
    skjevheten modulen er bygget mot, snudd inn i erklæringsmekanismen.
    """
    order = {TaskClass.BL: 0, TaskClass.DOUBT: 1, TaskClass.ADR: 2}
    silent = TaskClassifier().classify(clean_bl_proposal(
        title="Utvid Faber med steg 13", description="steg 13 landing",
        declared_trust_boundary_change=None, declared_new_register=None))
    honest = TaskClassifier().classify(clean_bl_proposal(
        title="Utvid Faber med steg 13", description="steg 13 landing",
        declared_trust_boundary_change=True, declared_new_register=True))
    assert order[honest.task_class] >= order[silent.task_class]


# --- reviewer-funn B2: contract_ref var en kontroll som ikke kunne feile ---

@pytest.mark.parametrize("junk", ["n/a", "TBD", "none", "x", "0", "ikke relevant",
                                  "se over", "-", "ja"])
def test_prose_in_the_contract_field_is_not_a_contract(junk):
    """REVIEWER-FUNN, og det skarpeste i hele reviewen.

    Første utkast sjekket bare `.strip()`, så alle disse nådde BL. Modulens
    egen docstring fordømmer nøyaktig dette om ADR-nummeret — og bygget så
    kvitteringsfeltet ett argument bortenfor.
    """
    result = TaskClassifier().classify(clean_bl_proposal(contract_ref=junk))
    assert result.task_class is TaskClass.DOUBT
    hit = next(h for h in result.hits if h.signal is Signal.MISSING_CONTRACT_REF)
    assert junk in hit.evidence, "evidensen skal vise hva som faktisk sto der"


@pytest.mark.parametrize("ref,kind", [
    ("ADR-047-F5 (akseptert)", "ADR"),
    ("ADR-062", "ADR"),
    ("BL-4029", "BL"),
    ("CAD-D10", "CAD"),
    ("hermes_cli.kanban_db.dispatch_lock (eksisterende)", "modul/symbol"),
    ("agent.code_workflow.ScopeBudget", "modul/symbol"),
    ("agent/code_workflow.py", "fil"),
])
def test_a_named_contract_is_recognised(ref, kind):
    assert parse_contract_ref(ref) == kind
    assert TaskClassifier().classify(
        clean_bl_proposal(contract_ref=ref)).task_class is TaskClass.BL


@pytest.mark.parametrize("junk", [
    "n.a", "N.A", "1.0", "v1.2.3", "2026.08.11",
    "no.contract", "null.null", "tbd.tbd",
    "README.md", "image.png", "notes.docx",
    "e.g. dette bor i eksisterende kode",
])
def test_adding_a_dot_does_not_turn_prose_into_a_contract(junk):
    """REVIEWER-FUNN N1: baren gikk fra «ikke-tom streng» til «streng med
    punktum i».

    Alle disse kjøpte BL. Et modul-symbol må nå starte i en toppnivå-pakke som
    FINNES i dette repoet — et lokalt strukturelt faktum, ikke et oppslag i
    registeret på .13, så sirkulariteten fra ADR-062 V4 kommer ikke tilbake.
    """
    assert parse_contract_ref(junk) is None
    assert TaskClassifier().classify(
        clean_bl_proposal(contract_ref=junk)).task_class is TaskClass.DOUBT


def test_repo_packages_matches_the_real_importable_packages():
    """DRIFTVAKTEN, og den hører hjemme HER, ikke i modulen.

    `_REPO_PACKAGES` er en snapshot. Modulen leser bevisst ikke filsystemet ved
    import — en sideeffektfri modul skal ikke avhenge av cwd — så snapshoten
    kan drifte når en pakke legges til eller døpes om, og driften snevrer inn
    klassifisereren i stillhet.

    Testen kan lese filsystemet gratis. REVIEWER-FUNN F2: første versjon var
    `ls -d */` håndnormalisert til understrek, og normaliseringen fant opp
    fire modulrøtter som ikke kan finnes (`mcp`, `optional_mcps`,
    `optional_skills`, `ui_tui` — de ekte katalogene har bindestrek og er
    derfor ikke importerbare). Feilretningen var TILLATENDE. Riktig univers er
    katalogene med `__init__.py`.
    """
    from agent.task_classifier import _REPO_PACKAGES

    root = Path(__file__).resolve().parent.parent
    actual = {d.name for d in root.iterdir()
              if d.is_dir() and (d / "__init__.py").exists()}
    assert set(_REPO_PACKAGES) == actual, (
        "_REPO_PACKAGES har driftet fra repoets faktiske importerbare pakker; "
        f"kun i settet: {sorted(set(_REPO_PACKAGES) - actual)}, "
        f"kun på disk: {sorted(actual - set(_REPO_PACKAGES))}")


def test_the_file_form_is_reachable_and_its_whitelist_is_not_dead_code():
    """REVIEWER-FUNN N1, følgeskade: den prikk-baserte regelen sto først og
    slukte hvert filnavn, så `image.png` ble godtatt som «modul/symbol» og
    utvidelses-hvitelisten ble aldri konsultert."""
    assert parse_contract_ref("tools/allocate_adr.py") == "fil"
    assert parse_contract_ref("image.png") is None


def test_a_citation_buried_inside_an_excuse_does_not_count():
    """Referansen matches fra STARTEN, ikke hvor som helst i strengen."""
    assert parse_contract_ref("n/a — se ADR-999 hvis du vil") is None


def test_parse_contract_ref_checks_form_not_existence():
    """`ADR-999` finnes ikke, men FORMEN er gyldig.

    Eksistens er `DesignGate` (steg 7) sin jobb, mot det ekte registeret på
    .13. Å påstå noe mer her ville vært nok en kontroll som ikke kan feile.
    """
    assert parse_contract_ref("ADR-999") == "ADR"


def test_you_cannot_declare_your_way_out_of_a_word_you_wrote():
    """Erklæring «nei» + ordlyd «ja» er DOUBT, ikke uavgjort løst til erklæringen."""
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Liten opprydding i autonomi-grensen",
        declared_trust_boundary_change=False,
    ))
    assert result.task_class is TaskClass.ADR  # ordlyden alene er nok
    disagreement = [h for h in result.hits
                    if h.signal is Signal.TEXT_STRUCTURE_DISAGREEMENT]
    assert disagreement, "uenigheten mellom erklæring og tekst skal registreres"
    assert "overprøver ikke" in disagreement[0].evidence


def test_declared_no_register_against_a_register_diff_is_recorded_as_disagreement():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Rydd i grafskjema",
        description="Ingen nye ting.",
        diff_text="CREATE CONSTRAINT thing_id FOR (t:Thing) REQUIRE t.id IS UNIQUE",
        declared_new_register=False,
    ))
    assert result.task_class is TaskClass.ADR
    assert any(h.signal is Signal.TEXT_STRUCTURE_DISAGREEMENT for h in result.hits)


# ---------------------------------------------------------------------------
# 4. Den strukturelle påstanden: ingenting kan tale FOR den billige klassen.
# ---------------------------------------------------------------------------

# --- reviewer-funn B5: substring-matching gjorde ADR til standardklassen ---

@pytest.mark.parametrize("innocent", [
    "Vi holder på med dette i dag",            # «doing» ~ «doi»
    "We are doing this today",                 # «doing» ~ «doi»
    "Planleggeren encounters en stall",        # «encounter» ~ «counter»
    "Oppdater etiketten på EierskapPage",      # «eierskap» — strøket helt
    "Rett en skrivefeil i README",
])
def test_ordinary_prose_does_not_become_an_architectural_decision(innocent):
    """REVIEWER-FUNN, målt på ekte setninger.

    Et leksikalsk lag uten ordgrenser gjør ADR til standardklassen — den
    motsatte feilen av den modulen er bygget mot, ikke en trygg versjon av den.
    """
    result = TaskClassifier().classify(clean_bl_proposal(
        title=innocent, description=innocent))
    assert result.task_class is TaskClass.BL, [h.evidence for h in result.hits]


@pytest.mark.parametrize("real", [
    "Vi skal minte en DOI for artikkelen",
    "Endre systemctl-enheten",
    "Autonom læringsløyfe uten godkjenning",
    "Innfør et nytt register for oppgaver",
])
def test_the_real_terms_still_fire_after_the_boundaries_were_added(real):
    """Presisjon uten sensitivitet er bare en gate som aldri fyrer."""
    result = TaskClassifier().classify(clean_bl_proposal(
        title=real, description=real))
    assert result.task_class is TaskClass.ADR, [h.evidence for h in result.hits]


# --- reviewer-funn B4: DOI-detektoren hadde presisjonen snudd -------------

@pytest.mark.parametrize("diff", [
    "resp = mint_doi(record)",
    "figshare.mint_doi()",
    "resp = mint_doi_for(article_id)",
    "x = mint_new_doi(record)",
    "doi_minter(record)",
    # REVIEWER-FUNN N2 — argumentnavnet er det VANLIGE tilfellet, og
    # `client.mint(doi_payload)` traff FØR jeg «fikset» mønsteret. Jeg rettet
    # den avsluttende `\\b` på to grener og lot den stå på den tredje.
    "client.mint(doi_payload)",
    "figshare.mint(doi_record)",
    "self.mint(article_doi)",
    "mint(new_doi)",
    "await client.mint(payload_doi)",
    "mint(build(x), doi)",
    # REVIEWER-FUNN F1 — understrek-prefiks er standard python-skrivemåte for
    # en privat metode, og `\\b` holder ikke midt i et ord.
    "def _mint_doi(self, record):",
    "self._mint_doi(record)",
    "obj._mint_new_doi(r)",
    "x = self._mint(doi_payload)",
    "await self._mint(article_doi)",
    "figshare_mint(doi)",
    "token_mint(doi)",
])
def test_the_actual_DOI_minting_call_is_caught(diff):
    """REVIEWER-FUNN: alle disse gikk fri fra det opprinnelige mønsteret."""
    result = TaskClassifier().classify(clean_bl_proposal(diff_text=diff))
    assert result.task_class is TaskClass.ADR
    assert any("hard-limit #1" in h.evidence for h in result.hits)


@pytest.mark.parametrize("diff", [
    "# DOI-håndtering: aldri mint her",
    "we are doing a mint julep test",
    "+ print(doing_minutes)",
    "mint(payload)",
    "counter.mint(tokens)",
])
def test_a_comment_forbidding_the_call_is_not_the_call(diff):
    """Et mønster som bommer på kallet og treffer forbudet mot kallet
    beskytter feil retning."""
    hits = TaskClassifier().collect(clean_bl_proposal(diff_text=diff))
    assert not [h for h in hits if "hard-limit #1" in h.evidence]


# --- reviewer-funn B6: `/cron/` bommet på toppnivå-`cron/` ---------------

@pytest.mark.parametrize("path", ["cron/suggestions.py", "agent/cron/x.py",
                                  "etc/crontab"])
def test_scheduled_execution_paths_are_hard_limit_wherever_they_sit(path):
    """Et falskt NEGATIV på en hard-limit feiler i feil retning."""
    result = TaskClassifier().classify(clean_bl_proposal(touched_paths=(path,)))
    assert result.task_class is TaskClass.ADR


def test_no_signal_can_argue_for_the_cheap_class():
    """Det finnes ingen ``Disposition.BL``, og det er ikke en forglemmelse.

    Et signal som kunne si «dette er BL» ville vært en vei for ett funn til å
    oppheve et annet, og den veien går alltid nedover i kostnad.
    """
    assert not hasattr(Disposition, "BL")
    assert {d.value for d in Disposition} == {"adr", "doubt", "design_review"}


def test_every_hit_a_real_proposal_produces_points_upward():
    hits = TaskClassifier().collect(clean_bl_proposal(
        title="Endre tillitsgrense og slett alt",
        reversibility=Reversibility.UNKNOWN,
        contract_ref="",
        declared_trust_boundary_change=None,
        declared_new_register=None,
    ))
    assert hits
    assert all(h.disposition in {Disposition.ADR, Disposition.DOUBT,
                                 Disposition.DESIGN_REVIEW} for h in hits)


# ---------------------------------------------------------------------------
# 5. Blast-radius: anslag på steg 3, måling på steg 8, skralle imellom.
# ---------------------------------------------------------------------------

def test_missing_blast_radius_estimate_does_not_block_at_step_3():
    """Diffen finnes ikke på steg 3. Å kreve den her er ADR-062 V4-sirkulariteten."""
    result = TaskClassifier().classify(clean_bl_proposal(
        estimated_changed_files=None, estimated_changed_lines=None))
    assert result.task_class is TaskClass.BL
    assert not any(h.signal is Signal.BLAST_RADIUS for h in result.hits)


def test_estimate_over_budget_stays_BL_but_forces_design_review():
    """Morten: «blast-radius over terskel -> minst design-review». Minst, ikke ADR."""
    result = TaskClassifier(ScopeBudget()).classify(clean_bl_proposal(
        estimated_changed_files=40, estimated_changed_lines=4000))
    assert result.task_class is TaskClass.BL
    assert result.design_review_required is True
    assert any(h.signal is Signal.BLAST_RADIUS for h in result.hits)


def test_measured_scope_over_budget_forces_design_review_at_step_8():
    clf = TaskClassifier()
    proposal = clean_bl_proposal()
    prior = clf.classify(proposal)
    assert prior.design_review_required is False

    after = clf.reclassify_on_measurement(prior, proposal, MeasuredScope(
        changed_files=42, changed_lines=5000, touched_paths=("a.py",)))
    assert after.design_review_required is True


def test_the_ratchet_cannot_be_loosened_by_a_small_diff():
    """En ADR på steg 3 blir ikke BL på steg 8 fordi diffen ble liten."""
    clf = TaskClassifier()
    proposal = clean_bl_proposal(
        title="Flytt autonomi-grensen", declared_trust_boundary_change=True)
    prior = clf.classify(proposal)
    assert prior.task_class is TaskClass.ADR

    after = clf.reclassify_on_measurement(prior, proposal, MeasuredScope(
        changed_files=1, changed_lines=2, touched_paths=("tiny.py",)))
    assert after.task_class is TaskClass.ADR


def test_a_triggered_design_review_is_never_cancelled():
    clf = TaskClassifier()
    proposal = clean_bl_proposal(
        estimated_changed_files=40, estimated_changed_lines=4000)
    prior = clf.classify(proposal)
    assert prior.design_review_required is True

    after = clf.reclassify_on_measurement(prior, proposal, MeasuredScope(
        changed_files=1, changed_lines=3, touched_paths=("tiny.py",)))
    assert after.design_review_required is True


def test_the_measured_diff_can_escalate_what_the_estimate_hid():
    """Steg 3 så en ryddejobb. Steg 8 ser en ``DETACH DELETE``."""
    clf = TaskClassifier()
    proposal = clean_bl_proposal(title="Rydd i noder", description="Liten opprydding.")
    prior = clf.classify(proposal)
    assert prior.task_class is TaskClass.BL

    after = clf.reclassify_on_measurement(prior, proposal, MeasuredScope(
        changed_files=1, changed_lines=4,
        touched_paths=("tools/cleanup.py",),
        diff_text="+    session.run('MATCH (n:Old) DETACH DELETE n')"))
    assert after.task_class is TaskClass.ADR


# ---------------------------------------------------------------------------
# 6. ADR-numre: klassifisereren deler ikke ut noen, og tåler flere filer.
# ---------------------------------------------------------------------------

def test_the_classifier_names_the_allocator_and_mints_nothing():
    """BL-3824: fem numre tatt for hånd i én time fordi regelen bare navnga
    BL-varianten. Så ADR-varianten navngis her, og ingen streng i resultatet
    er et nummer."""
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Ny tillitsgrense mot .12", declared_trust_boundary_change=True))
    assert result.requires_adr_allocation is True
    assert ADR_ALLOCATOR_CMD in result.next_action
    assert "allocate_adr" in result.next_action

    import re
    blob = repr(result.as_dict())
    minted = [m for m in re.findall(r"ADR-\d{3}", blob) if m != "ADR-062"]
    assert not minted, f"klassifisereren delte ut et nummer: {minted}"


@pytest.mark.parametrize("ref,expected", [
    ("ADR-047", (47, None)),
    ("ADR-047-F5", (47, 5)),
    ("adr-042", (42, None)),
    ("ADR-062", (62, None)),
    ("ADR-1000", (1000, None)),
])
def test_parse_adr_ref_accepts_both_the_bare_and_the_phase_citation_form(ref, expected):
    assert parse_adr_ref(ref) == expected


@pytest.mark.parametrize("ref", [
    "ADR", "ADR-", "BL-4056", "", "ADR-4x7",
    "ADR-047-F5-landing", "ADR-042/043", "ADR-047\nJUNK",
    pytest.param("ADR-0047", id="leading-zero-is-not-silently-normalised"),
    pytest.param("ADR-٠٤٧", id="unicode-digits-are-not-ascii-digits"),
])
def test_parse_adr_ref_rejects_what_is_not_a_ref(ref):
    """De to siste er reviewer-funn: `ADR-0047` ble stille normalisert til 47,
    og arabisk-indiske sifre ble tolket som tall fordi `\\d` er unicode-bred.
    En feilskrevet referanse skal si fra, ikke bli rettet til en annen ADR."""
    assert parse_adr_ref(ref) is None


def test_one_ADR_number_carried_by_several_documents_is_not_a_collision():
    """ADR-042/043/047 bæres av to filer hver i dag; ADR-047 er én beslutning
    i fem faser og skal ikke renummereres. Referansetolkeren har derfor ingen
    mening om hvor mange filer som finnes — den teller ikke."""
    assert parse_adr_ref("ADR-047") == parse_adr_ref("ADR-047")
    assert parse_adr_ref("ADR-047-F5")[0] == parse_adr_ref("ADR-047")[0]


def test_an_accepted_ADR_is_a_valid_existing_contract_for_BL_work():
    """Å implementere et allerede fattet vedtak er BL-arbeid.

    Men merk hva den IKKE gjør nedenfor: den opphever ikke et ADR-signal.
    """
    result = TaskClassifier().classify(clean_bl_proposal(
        contract_ref="ADR-047-F5 (akseptert)"))
    assert result.task_class is TaskClass.BL


def test_citing_an_ADR_does_not_launder_an_ADR_class_task_into_BL():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Flytt autonomi-grensen ett hakk",
        contract_ref="ADR-062 (akseptert)",
        declared_trust_boundary_change=True))
    assert result.task_class is TaskClass.ADR


# ---------------------------------------------------------------------------
# 7. Den uavhengige vurdereren.
# ---------------------------------------------------------------------------

def test_independence_is_delegated_not_reimplemented():
    """BL-4055 (`d6c7eb148`) eier regelen; denne modulen har ingen egen mening.

    To uavhengighets-sjekker med ulike signaturer og ulike feiltekster i samme
    tre er den divergensen banneret i `code_workflow.py` dokumenterer — og som
    denne modulen selv brukte som argument for en Protocol framfor enda en
    HTTP-klient.
    """
    import agent.task_classifier as tc
    import agent.second_opinion as so

    assert not hasattr(tc, "ReviewerIdentity")
    assert not hasattr(tc, "_OPUS_MODEL_RE")
    assert tc.assert_independent_reviewer(
        provenance=so.INDEPENDENT_PROVENANCE, model="claude-opus-5") == (True, "")


@pytest.mark.parametrize("provenance,model", [
    ("cortex.local", "claude-opus-5"),
    ("anthropic.api", "claude-haiku-4-5-20251001"),
    ("anthropic.api", "claude-sonnet-opus-mimic"),
    ("anthropic.api", ""),
])
def test_a_non_independent_reviewer_is_refused_with_a_reason(provenance, model):
    ok, reason = assert_independent_reviewer(provenance=provenance, model=model)
    assert not ok
    assert reason, "en avvisning uten begrunnelse kan ingen handle på"


def test_a_missing_reviewer_escalates_and_never_passes():
    """Ikke-utført er ikke bestått — samme regel som steg 11/12/13."""
    outcome = UnavailableReviewer().review(DesignReviewRequest(
        proposal=clean_bl_proposal(),
        classification=TaskClassifier().classify(clean_bl_proposal())))
    assert outcome.verdict == "ESCALATE"
    assert outcome.verdict != "PASS"
    assert "Ikke-utført er ikke bestått" in outcome.reasons[0]


# ---------------------------------------------------------------------------
# 8. Serialisering — klassifiseringen skal kunne lagres med evidensen sin.
# ---------------------------------------------------------------------------

def test_the_classification_serialises_with_the_evidence_that_produced_it():
    result = TaskClassifier().classify(clean_bl_proposal(
        title="Endre tillitsgrense", declared_trust_boundary_change=True))
    blob = result.as_dict()
    assert blob["task_class"] == "ADR"
    assert blob["hits"], "signalene skal lagres, ikke bare dommen"
    assert all({"signal", "disposition", "evidence", "source"} <= set(h)
               for h in blob["hits"])


def test_a_clean_BL_records_that_the_signals_were_consulted():
    """Fraværet av treff er et registrert faktum, ikke en stillhet."""
    result = TaskClassifier().classify(clean_bl_proposal())
    assert isinstance(result, Classification)
    assert result.reasons
    assert "ingen signal fyrte" in result.reasons[0]


# ---------------------------------------------------------------------------
# 9. Adapteren fra Faber-målet (agent/faber_control_bridge.py).
#
# Broen laster MWPs kontrollplan på filsti ved import. Der det ikke finnes,
# er det ingenting å teste — men det skal si HVORFOR, ikke bli grønt i stillhet.
# ---------------------------------------------------------------------------

bridge = pytest.importorskip(
    "agent.faber_control_bridge",
    reason="MWPs kontrollplan (MWP_REPO) er ikke tilgjengelig her")


GOAL = {
    "goal_id": "faber.code.flyby:eksempel",
    "title": "Rett feilmelding i kanban-dispatch-låsen",
    "rollback": "git revert av commiten",
    "next_step": "Legg til holder-id i loggmeldingen.",
    "evidence": {
        "repo_scope": "hermes-agent: hermes_cli/kanban_db.py, 20-minute scheduler",
        "gate_class": "reviewer/landing gate",
        "contract_ref": "hermes_cli.kanban_db.dispatch_lock",
        "trust_boundary_change": "nei",
        "new_register": "nei",
    },
}


def test_a_fully_answered_goal_classifies_as_BL():
    """Falsifikatoren igjen, denne gangen gjennom den ekte adapteren."""
    result = TaskClassifier().classify(bridge.proposal_from_goal(GOAL))
    assert result.task_class is TaskClass.BL


def test_scope_text_yields_paths_and_leaves_prose_alone():
    """«20-minute scheduler» er ikke en sti og skal ikke bli til en.

    Feil-retningen er bevisst: et ugjenkjennelig fragment utelates fra det
    MÅLTE grunnlaget i stedet for å gjettes inn i det.
    """
    proposal = bridge.proposal_from_goal(GOAL)
    assert proposal.touched_paths == ("hermes_cli/kanban_db.py",)


@pytest.mark.parametrize("raw", ["", "unknown", "kanskje", None, "n/a"])
def test_anything_that_is_not_a_clear_no_stays_unanswered(raw):
    """«unknown» er ikke «nei». Tri-state, ikke boolsk med default."""
    goal = {**GOAL, "evidence": {**GOAL["evidence"], "trust_boundary_change": raw}}
    proposal = bridge.proposal_from_goal(goal)
    assert proposal.declared_trust_boundary_change is None
    assert TaskClassifier().classify(proposal).task_class is TaskClass.DOUBT


@pytest.mark.parametrize("raw,expected", [(False, False), (True, True), (0, False)])
def test_a_real_json_boolean_survives_the_adapter(raw, expected):
    """REVIEWER-FUNN B3: `str(value or "")` gjorde `False` til `""` til `None`.

    En erklært `nei` var dermed umulig å uttrykke gjennom broen — og
    0-BL-målingen var delvis en parser-artefakt.
    """
    goal = {**GOAL, "evidence": {**GOAL["evidence"], "trust_boundary_change": raw}}
    assert bridge.proposal_from_goal(goal).declared_trust_boundary_change is expected


def test_a_goal_without_a_rollback_has_unknown_reversibility():
    goal = {**GOAL, "rollback": ""}
    proposal = bridge.proposal_from_goal(goal)
    assert proposal.reversibility is Reversibility.UNKNOWN
    assert TaskClassifier().classify(proposal).task_class is TaskClass.DOUBT


def test_the_seven_live_goals_do_not_all_collapse_into_one_class():
    """MÅLT 2026-08-11: 2 ADR, 5 DOUBT, 0 BL av sju levende mål.

    Testen fester ikke tallene — målene endrer seg. Den fester det som ville
    gjort klassifisereren verdiløs i BEGGE retninger: at den svarer det samme
    på alt. `TRUST_TERMS` fyrte på 2 av 7, ikke 7 av 7.
    """
    goals = [
        GOAL,
        {**GOAL, "title": "Lukket sporbar autonom læringsløyfe"},
        {**GOAL, "title": "Rydd i logger", "rollback": ""},
    ]
    classes = {TaskClassifier().classify(bridge.proposal_from_goal(g)).task_class
               for g in goals}
    assert len(classes) > 1, "en klassifiserer som svarer det samme på alt skiller ingenting"
