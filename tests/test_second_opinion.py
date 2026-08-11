"""BL-4055: second opinion -- utloeser, uenighetspolitikk, fail-closed, noekkelfil."""
from __future__ import annotations

import os

import pytest

from agent.second_opinion import (
    INDEPENDENT_PROVENANCE,
    ChangeUnderReview,
    SecondOpinionOutcome,
    SecondOpinionStatus,
    SecondOpinionTrigger,
    assert_independent,
    normalise_reply,
    resolve_disagreement,
)
from agent import second_opinion_client as soc


def _change(**over) -> ChangeUnderReview:
    base = dict(diff_id="d1", reviewer="faber.codex", verdict="PASS",
                confidence=0.95, changed_files=1, changed_lines=10,
                landing_set=("agent/hello.py",), bl_ref="BL-4055")
    base.update(over)
    return ChangeUnderReview(**base)


# --------------------------------------------------------------------------
# UTLOESEREN. Den avgjoerende egenskapen: den fyrer OGSAA naar reviewer er
# selvsikker, ellers kalles den aldri naar man tar feil med selvtillit.
# --------------------------------------------------------------------------

def test_small_high_confidence_change_does_not_trigger():
    assert not SecondOpinionTrigger().evaluate(_change()).required


def test_low_confidence_triggers():
    d = SecondOpinionTrigger().evaluate(_change(confidence=0.4))
    assert d.required and any(r.startswith("confidence_below") for r in d.reasons)


@pytest.mark.parametrize("value", [None, "", "n/a", float("nan"), True])
def test_unmeasured_confidence_triggers(value):
    """Fravaer av data er ikke et positivt funn -- umaalt er ikke hoeyt."""
    d = SecondOpinionTrigger().evaluate(_change(confidence=value))
    assert d.required and "confidence_unmeasured" in d.reasons


def test_blast_radius_triggers_despite_maximum_confidence():
    """DETTE er testen som gjoer andre-meningen ekte.

    En stor endring med confidence 1.0 er nettopp «selvsikker og potensielt
    gal». Hvis denne slipper gjennom, er utloeseren bare et tvil-flagg.
    """
    d = SecondOpinionTrigger().evaluate(
        _change(confidence=1.0, changed_files=9, changed_lines=800))
    assert d.required
    assert any(r.startswith("blast_radius_files") for r in d.reasons)
    assert any(r.startswith("blast_radius_lines") for r in d.reasons)


def test_governance_surface_triggers_despite_maximum_confidence():
    d = SecondOpinionTrigger().evaluate(
        _change(confidence=1.0, changed_files=1, changed_lines=3,
                landing_set=("agent/code_workflow.py",)))
    assert d.required
    assert any(r.startswith("governance_surface") for r in d.reasons)


def test_unmeasured_blast_radius_triggers():
    d = SecondOpinionTrigger().evaluate(_change(changed_files=None, changed_lines=None))
    assert d.required and "blast_radius_unmeasured" in d.reasons


# --------------------------------------------------------------------------
# UENIGHETSPOLITIKKEN
# --------------------------------------------------------------------------

def _outcome(status, **over) -> SecondOpinionOutcome:
    base = dict(status=status, reason="r", provenance=INDEPENDENT_PROVENANCE,
                model="claude-opus-5", confidence=0.9)
    base.update(over)
    return SecondOpinionOutcome(**base)


def test_concur_on_pass_allows():
    r = resolve_disagreement(change=_change(),
                             opinion=_outcome(SecondOpinionStatus.CONCUR))
    assert r.allow and not r.escalate_to_owner


def test_dissent_blocks():
    r = resolve_disagreement(change=_change(),
                             opinion=_outcome(SecondOpinionStatus.DISSENT))
    assert not r.allow and r.gate == "second_opinion_dissent"


def test_escalate_goes_to_owner():
    r = resolve_disagreement(change=_change(),
                             opinion=_outcome(SecondOpinionStatus.ESCALATE))
    assert not r.allow and r.escalate_to_owner


def test_unavailable_blocks_and_is_distinguishable_from_dissent():
    """Manglende svar og uenighet blokkerer begge, men av ULIKE grunner."""
    r = resolve_disagreement(
        change=_change(),
        opinion=SecondOpinionOutcome.unavailable("timeout"))
    assert not r.allow
    assert r.gate == "second_opinion_unavailable"
    assert r.gate != "second_opinion_dissent"


def test_concur_never_upgrades_a_block():
    """En andre mening kan nedlegge veto, aldri stemple."""
    r = resolve_disagreement(change=_change(verdict="BLOCK"),
                             opinion=_outcome(SecondOpinionStatus.CONCUR))
    assert not r.allow and r.gate == "second_opinion_cannot_upgrade"


@pytest.mark.parametrize("status", list(SecondOpinionStatus))
def test_both_votes_are_always_recorded(status):
    """Ogsaa ved enighet. Logging er ubetinget, ikke uenighetspolitikken."""
    opinion = (SecondOpinionOutcome.unavailable("x")
               if status is SecondOpinionStatus.UNAVAILABLE else _outcome(status))
    r = resolve_disagreement(change=_change(), opinion=opinion)
    assert "reviewer" in r.votes and "second_opinion" in r.votes
    assert "faber.codex" in r.votes["reviewer"]


# --------------------------------------------------------------------------
# UAVHENGIGHET + NORMALISERING (fail-closed)
# --------------------------------------------------------------------------

def test_cortex_provenance_is_not_a_second_opinion():
    assert assert_independent(provenance="cortex.local", model="claude-opus-5")
    assert assert_independent(provenance=INDEPENDENT_PROVENANCE, model="qwen-235b")
    assert not assert_independent(provenance=INDEPENDENT_PROVENANCE, model="claude-opus-5")


@pytest.mark.parametrize("payload", [
    None, "not a mapping", {}, {"status": "MAYBE"},
    {"status": "UNAVAILABLE"},                       # kan ikke erklaere seg selv utilgjengelig
    {"status": "DISSENT"},                           # uenighet uten begrunnelse
    {"status": "DISSENT", "reason": "", "findings": []},
])
def test_malformed_replies_are_unavailable_not_pass(payload):
    out = normalise_reply(payload, provenance=INDEPENDENT_PROVENANCE, model="claude-opus-5")
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert not out.is_pass


def test_non_independent_reply_is_rejected_even_when_it_concurs():
    out = normalise_reply({"status": "CONCUR"}, provenance="cortex.local",
                          model="claude-opus-5")
    assert out.status is SecondOpinionStatus.UNAVAILABLE


def test_well_formed_dissent_is_parsed():
    out = normalise_reply(
        {"status": "DISSENT", "reason": "unbounded retry", "confidence": 0.8,
         "findings": ["retry loop has no ceiling"]},
        provenance=INDEPENDENT_PROVENANCE, model="claude-opus-5")
    assert out.status is SecondOpinionStatus.DISSENT
    assert out.findings == ("retry loop has no ceiling",)


def test_concur_without_reason_is_accepted():
    out = normalise_reply({"status": "CONCUR", "confidence": 0.9},
                          provenance=INDEPENDENT_PROVENANCE, model="claude-opus-5")
    assert out.is_pass


# --------------------------------------------------------------------------
# NOEKKELFILA: 0600 + eier. Feil modus = INGEN konfigurasjon.
# --------------------------------------------------------------------------

def _keyfile(tmp_path, mode=0o600, content="sk-ant-test"):
    p = tmp_path / "key"
    p.write_text(content)
    os.chmod(p, mode)
    return p


def test_key_is_read_when_mode_is_0600(tmp_path):
    key, reason = soc._read_key_file(_keyfile(tmp_path))
    assert key == "sk-ant-test" and reason == ""


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o604, 0o666, 0o640])
def test_group_or_other_readable_key_is_refused(tmp_path, mode):
    key, reason = soc._read_key_file(_keyfile(tmp_path, mode=mode))
    assert key == "" and "0600" in reason


def test_missing_key_file_is_refused(tmp_path):
    key, reason = soc._read_key_file(tmp_path / "absent")
    assert key == "" and "does not exist" in reason


def test_empty_key_file_is_refused(tmp_path):
    key, reason = soc._read_key_file(_keyfile(tmp_path, content="   \n"))
    assert key == "" and "empty" in reason


def test_key_owned_by_another_uid_is_refused(tmp_path, monkeypatch):
    """Eier-sjekken, ikke bare modus-sjekken.

    En fil en ANNEN part eier og selv har chmod-et til 0600 bestaar en ren
    modus-sjekk. Da leser vi et kreditiv vi ikke vet hvor kom fra.
    """
    path = _keyfile(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(path).st_uid + 12345)
    key, reason = soc._read_key_file(path)
    assert key == "" and "owned by uid" in reason


# --------------------------------------------------------------------------
# TRANSPORTEN: hver feilvei ender i UNAVAILABLE, aldri i en bestaatt sjekk.
# --------------------------------------------------------------------------

def test_missing_key_yields_unavailable_not_pass(tmp_path):
    out = soc.fetch_second_opinion(_change(), diff_text="x", key_file=tmp_path / "absent")
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_credential"


def test_base_url_pointing_away_from_anthropic_is_refused(tmp_path, monkeypatch):
    """Mortens direktiv, mekanisk: ikke cortex-modellen paa .13:1234."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://192.168.40.13:1234/v1")
    out = soc.fetch_second_opinion(_change(), diff_text="x",
                                   key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_independence"


def test_empty_diff_is_not_no_objection(tmp_path):
    out = soc.fetch_second_opinion(_change(), diff_text="   ",
                                   key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_input"


def test_oversized_diff_is_refused(tmp_path):
    out = soc.fetch_second_opinion(_change(), diff_text="x" * (soc.MAX_REVIEW_CHARS + 1),
                                   key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_input"


def test_api_exception_yields_unavailable(tmp_path, monkeypatch):
    class _Boom:
        def __init__(self, **_):
            raise TimeoutError("upstream timed out")

    monkeypatch.setattr("anthropic.Anthropic", _Boom)
    out = soc.fetch_second_opinion(_change(), diff_text="diff --git a b",
                                   key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_transport"


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, text="", stop_reason="end_turn", model="claude-opus-5"):
        self.content = [_Block(text)] if text else []
        self.stop_reason = stop_reason
        self.model = model


def _stub_api(monkeypatch, response):
    class _Msgs:
        def create(self, **_):
            return response

    class _Client:
        def __init__(self, **_):
            self.messages = _Msgs()

    monkeypatch.setattr("anthropic.Anthropic", _Client)


def test_non_json_reply_yields_unavailable(tmp_path, monkeypatch):
    _stub_api(monkeypatch, _Resp(text="Looks fine to me!"))
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE


def test_invalid_json_reply_yields_unavailable(tmp_path, monkeypatch):
    _stub_api(monkeypatch, _Resp(text='{"status": "CONCUR",,,}'))
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE


def test_refusal_stop_reason_yields_unavailable(tmp_path, monkeypatch):
    _stub_api(monkeypatch, _Resp(text="", stop_reason="refusal"))
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_refusal"


def test_truncated_reply_yields_unavailable(tmp_path, monkeypatch):
    _stub_api(monkeypatch, _Resp(text='{"status": "CONC', stop_reason="max_tokens"))
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_transport"


def test_model_that_is_not_opus_is_refused_even_on_concur(tmp_path, monkeypatch):
    _stub_api(monkeypatch, _Resp(text='{"status": "CONCUR"}', model="qwen3-235b"))
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_independence"


def test_well_formed_concur_round_trips(tmp_path, monkeypatch):
    _stub_api(monkeypatch, _Resp(
        text='Sure. {"status": "CONCUR", "reason": "checked", "confidence": 0.88}'))
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.is_pass and out.confidence == 0.88
    assert out.provenance == INDEPENDENT_PROVENANCE


# --------------------------------------------------------------------------
# GUI-RUTA (.15:9119). Handleren testes direkte -- HTTP-stakken tilfoerer
# ingenting til det som skal holdes fast her, og auth-egenskapen sjekkes
# eksplisitt i sin egen test i stedet for aa antas av et 200-svar.
# --------------------------------------------------------------------------

def _call_route(**over):
    import asyncio

    from hermes_cli.web_models import SecondOpinionRequest
    from hermes_cli.web_server import faber_second_opinion

    body = dict(diff="diff --git a b", diff_id="d1", reviewer="faber.codex",
                verdict="PASS", confidence=0.95, changed_files=1,
                changed_lines=5, landing_set=["agent/hello.py"])
    body.update(over)
    return asyncio.run(faber_second_opinion(SecondOpinionRequest(**body)))


def test_route_is_not_public():
    """Ruta bruker en API-noekkel og koster penger -- den maa vaere autentisert."""
    from hermes_cli.web_server import _PUBLIC_API_PATHS

    assert "/api/faber/second-opinion" not in _PUBLIC_API_PATHS


def test_route_is_registered():
    from hermes_cli.web_server import app

    assert any(getattr(r, "path", "") == "/api/faber/second-opinion" for r in app.routes)


def test_route_does_not_spend_a_call_when_nothing_triggers():
    out = _call_route()
    assert out["triggered"] is False
    assert out["consulted"] is False          # ingen ble spurt ...
    assert out["gate"] == "second_opinion_not_triggered"


def test_route_reports_unavailable_as_block_not_pass(tmp_path, monkeypatch):
    """Fail-closed overlever HTTP-laget: ingen noekkel -> allow=False."""
    monkeypatch.setenv("SECOND_OPINION_API_KEY_FILE", str(tmp_path / "absent"))
    out = _call_route(changed_files=9, changed_lines=800)
    assert out["triggered"] is True
    assert out["status"] == "UNAVAILABLE"
    assert out["allow"] is False
    # Undergaten OVERLEVER. Foer kollapset alle UNAVAILABLE-aarsakene til én
    # verdi, og da var «vi fikk ikke svar» og «vi sendte aldri noe» det samme i
    # journalen -- selv om de krever helt ulike inngrep.
    assert out["gate"] == "second_opinion_credential"


def test_force_bypasses_the_trigger_but_not_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("SECOND_OPINION_API_KEY_FILE", str(tmp_path / "absent"))
    out = _call_route(force=True)
    assert out["triggered"] is False          # utloeseren fyrte ikke ...
    assert out["consulted"] is True           # ... men Morten spurte likevel
    assert out["reasons"] == ["forced_by_operator"]
    assert out["allow"] is False              # og fail-closed staar


# ==========================================================================
# REGRESJONER FRA REVIEWER-RUNDE 1 (BL-4055).
#
# Alle bugene under bestod den foerste testsuiten. Det er poenget med aa ha
# dem her: en 12/12 mutasjonsscore sa at testene fanget de bugene JEG hadde
# tenkt paa, ikke at det ikke fantes flere. Hver test her navngir den konkrete
# omgaaelsen reviewer FAKTISK reproduserte.
# ==========================================================================


@pytest.mark.parametrize("url", [
    # Lookalike-vert: en sannsynlig FEILKONFIGURASJON, ikke bare et angrep.
    "https://api.anthropic.com.cortex.lan/v1",
    # Fragment: verten ADR-en eksplisitt utelukker, med rett delstreng bakpaa.
    "http://192.168.40.13:1234/#api.anthropic.com",
    # Query og credentials -- samme delstreng-triks, andre plassering.
    "http://192.168.40.13:1234/v1?upstream=api.anthropic.com",
    "http://api.anthropic.com@192.168.40.13:1234/v1",
    "http://192.168.40.13:1234/v1",
])
def test_base_url_lookalikes_are_refused(tmp_path, monkeypatch, url):
    """Reviewer BLOCK 1: delstreng-testen ga en BESTAATT CONCUR fra cortex.

    En vertsidentitet maa parses, ikke soekes etter i en streng.
    """
    monkeypatch.setenv("ANTHROPIC_BASE_URL", url)
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_independence"


def test_real_anthropic_base_url_is_accepted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    assert soc._independent_base_url() == ""


def test_response_without_a_model_name_does_not_self_attest(tmp_path, monkeypatch):
    """Reviewer BLOCK 1: klienten falt tilbake paa navnet VI SPURTE OM.

    Da attesterte forespoerselen seg selv: enhver responder som bare utelot
    `model` fikk vaart oenskede navn skrevet inn i sin egen identitet.
    """
    class _NoModel(_Resp):
        def __init__(self):
            super().__init__(text='{"status": "CONCUR"}')
            del self.model

    _stub_api(monkeypatch, _NoModel())
    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.status is SecondOpinionStatus.UNAVAILABLE
    assert out.gate == "second_opinion_independence"


@pytest.mark.parametrize("model", [
    "claude-opus-4-1-cortexproxy",   # reviewer reproduserte NOEYAKTIG denne
    "claude-opus-proxy",
    "claude-opus-5-local",
    "claude-opus",
    "",
])
def test_model_names_that_only_look_like_opus_are_refused(model):
    """Et prefiks er en AAPEN mengde; en uavhengighetssjekk maa vaere lukket."""
    assert assert_independent(provenance=INDEPENDENT_PROVENANCE, model=model)


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-opus-4-8",
                                   "claude-opus-4-5-20251101"])
def test_real_opus_ids_are_accepted(model):
    assert not assert_independent(provenance=INDEPENDENT_PROVENANCE, model=model)


def test_resolve_enforces_independence_itself(tmp_path):
    """Reviewer BLOCK 2: gaten stolte paa at ingen andre lagde dens input.

    Uavhengighet laa bare i `normalise_reply`. Den som bestemmer landing maa
    haandheve sin EGEN forutsetning -- ellers ligger den utenfor gaten.
    """
    smuggled = SecondOpinionOutcome(
        status=SecondOpinionStatus.CONCUR, reason="looks fine",
        provenance="cortex.13:1234", model="qwen3-235b", confidence=0.99)
    r = resolve_disagreement(change=_change(), opinion=smuggled)
    assert not r.allow
    assert r.gate == "second_opinion_independence"


def test_resolve_still_allows_a_genuinely_independent_concur():
    r = resolve_disagreement(change=_change(),
                             opinion=_outcome(SecondOpinionStatus.CONCUR))
    assert r.allow


@pytest.mark.parametrize("path", [
    "agent/lease_authority.py", "agent/faber_landing.py",
    "agent/faber_live_adapter.py", "agent/faber_runtime.py",
    "agent/faber_implementer.py", "agent/faber_postcommit_adapters.py",
    "agent/faber_goal_state.py", "agent/faber_control_bridge.py",
    "hermes_cli/web_server.py",
])
def test_governance_surface_covers_the_whole_machinery(path):
    """Reviewer-funn 4: listen utelot lease-autoriteten, landings-eksekutoren,
    reviewer-adapteren og gatens EGEN HTTP-flate.

    T5 er en av de to utloeserne som skal fange «selvsikker og gal». Da maa
    den daekke maskineriet, ikke bare én fil.
    """
    d = SecondOpinionTrigger().evaluate(
        _change(confidence=1.0, changed_files=1, changed_lines=2,
                landing_set=(path,)))
    assert d.required, f"{path} is gate machinery but does not trigger"


def test_bare_escalate_still_reaches_the_owner():
    """Reviewer-funn 5: en begrunnelsesloes ESCALATE ble skrevet om til
    UNAVAILABLE. Begge blokkerer -- men bare den ene naar Morten, saa
    omskrivingen tapte nettopp signalet som skulle eskaleres.
    """
    out = normalise_reply({"status": "ESCALATE"},
                          provenance=INDEPENDENT_PROVENANCE, model="claude-opus-5")
    assert out.status is SecondOpinionStatus.ESCALATE
    r = resolve_disagreement(change=_change(), opinion=out)
    assert not r.allow and r.escalate_to_owner


def test_bare_dissent_is_still_refused():
    """Uendret: en DISSENT uten begrunnelse er ikke etterproevbar."""
    out = normalise_reply({"status": "DISSENT"},
                          provenance=INDEPENDENT_PROVENANCE, model="claude-opus-5")
    assert out.status is SecondOpinionStatus.UNAVAILABLE


@pytest.mark.parametrize("raw,expected", [
    ("abc", 120.0),      # typo -> default, ikke ValueError under import
    ("", 120.0),
    ("1", 5.0),          # klemt opp
    ("99999", 600.0),    # klemt ned
    ("45", 45.0),
])
def test_timeout_env_cannot_break_module_import(monkeypatch, raw, expected):
    """Reviewer-funn 6: `float(os.environ[...])` paa modulnivaa lot en skrivefeil
    kaste under IMPORT -- og naar `code_workflow` importerer denne modulen for
    aa haandheve steget, ville en typo tatt ned hele runneren.
    """
    monkeypatch.setenv("SECOND_OPINION_TIMEOUT", raw)
    assert soc._env_float("SECOND_OPINION_TIMEOUT", 120.0,
                          low=5.0, high=600.0) == expected


def test_client_is_pinned_to_anthropic_regardless_of_env(tmp_path, monkeypatch):
    """Andre laget av BLOCK 1: env-en faar ikke VELGE endepunkt.

    Overlevde runde 2 av mutasjonssveipen: aa fjerne ``base_url=`` fra
    konstruktoeren endret ingen test, fordi stubben aldri saa paa hva klienten
    ble bygget med. Da hviler hele uavhengigheten paa env-sjekken alene -- og
    poenget med to lag er nettopp at det ene ikke skal vaere eneste forsvar.

    ``ANTHROPIC_BASE_URL`` settes her til den EKTE verten, saa env-sjekken
    slipper igjennom og testen maaler bare det andre laget.
    """
    seen: dict = {}

    class _Client:
        def __init__(self, **kw):
            seen.update(kw)
            self.messages = type("M", (), {
                "create": lambda _self, **_: _Resp(text='{"status": "CONCUR"}')})()

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setattr("anthropic.Anthropic", _Client)

    out = soc.fetch_second_opinion(_change(), diff_text="d", key_file=_keyfile(tmp_path))
    assert out.is_pass
    from urllib.parse import urlsplit
    assert urlsplit(seen.get("base_url", "")).hostname == "api.anthropic.com", (
        "client was built without an explicit base_url — the SDK would then read "
        "ANTHROPIC_BASE_URL itself, and the environment would decide who the "
        "'independent reviewer' is")


def test_every_gate_the_module_can_emit_has_its_own_next_step():
    """Tabellen maa daekke ALT som faktisk sendes ut, ikke bare det jeg husket.

    Gatene hoestes fra KILDEN, ikke fra en haandskrevet liste: en liste her ville
    raatnet i det noen la til en ny `gate=`-verdi, og da ville den nye gaten falt
    stille tilbake paa default-teksten. Det er den stille varianten av defekten
    hele denne BL-en handler om -- handlingen finnes, men den som skal utfoere den
    faar en generisk setning i stedet.
    """
    import re as _re
    from pathlib import Path

    from agent import second_opinion as so_mod
    from agent.second_opinion import _NEXT_STEP, _NEXT_STEP_DEFAULT, next_step_for

    # Alle TRE modulene som kan sende ut en gate. `code_workflow` gjoer det i
    # `_consult_second_opinion` (``second_opinion_runtime``); uten den her laa én
    # av de tre utenfor vaktens rekkevidde.
    from agent import code_workflow as cw_mod

    sources = [Path(so_mod.__file__).read_text(encoding="utf-8"),
               Path(soc.__file__).read_text(encoding="utf-8"),
               Path(cw_mod.__file__).read_text(encoding="utf-8")]
    emitted = set()
    for src in sources:
        emitted |= set(_re.findall(r'gate=["\'](second_opinion[a-z_]*)["\']', src))

    assert emitted, "harvest found no gates — the guard would pass vacuously"

    # `second_opinion` (allow-stien) og `second_opinion_unavailable` (fabrikkens
    # default) trenger ingen egen handling: den foerste blokkerer ikke, den andre
    # er nettopp «ukjent aarsak», som default-teksten beskriver riktig.
    generic = {"second_opinion", "second_opinion_unavailable"}
    missing = sorted(g for g in emitted - generic if g not in _NEXT_STEP)
    assert not missing, (
        f"these gates fall through to the generic next_step: {missing} — "
        "add one action each to _NEXT_STEP")

    for gate in _NEXT_STEP:
        assert next_step_for(gate) != _NEXT_STEP_DEFAULT
        assert next_step_for(gate).strip()


def test_an_unknown_gate_still_gets_an_actionable_default():
    """Default er ikke tom. En tom next_step ser ut som «ingen handling kreves»."""
    from agent.second_opinion import next_step_for

    assert next_step_for("second_opinion_something_new").strip()
