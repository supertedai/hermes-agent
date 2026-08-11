"""Steg 6 «claim_and_lease» — BL-4059.

Hver test her svarer på ett spørsmål: **kan steg 6 rapportere en lease som tatt
uten at en lease faktisk ble tatt?** Det var tilstanden før modulen fantes —
gaten krevde en lease ingen tok, så den eneste veien gjennom var å skrive
`lease_ref` i `goals.json`, altså fabrikkere evidens.

Fire av testene er direkte avtrykk av feller som ble truffet 2026-08-10 under
byggingen av verifiseringssiden: exit-kode-kontrakten, det reserverte
`surface:`-navnerommet, foreldreløse leases etter et delvis claim, og at
UVERIFISERT ikke er «clear».
"""
from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.request

import pytest

from agent import lease_authority as la


class _Resp:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _http_error(code: int, payload: object) -> urllib.error.HTTPError:
    body = json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError("http://authority/x", code, "conflict", {},
                                  io.BytesIO(body))


class _Calls(list):
    """Kallene som ble gjort, med køen av svar testen har lagt opp."""

    def __init__(self) -> None:
        super().__init__()
        self.replies: list[object] = []


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """Fanger hvert HTTP-kall og lar testen bestemme svaret."""
    recorded = _Calls()
    monkeypatch.setenv("SURFACE_RECEIPT_TOKEN", "test-token")

    def fake_urlopen(req: urllib.request.Request, timeout: float = 0):
        recorded.append(req)
        reply = recorded.replies.pop(0) if recorded.replies else _Resp(200, {})
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return recorded


def _body(req: urllib.request.Request) -> dict:
    return json.loads(req.data.decode("utf-8"))


# ---------------------------------------------------------------- fravær


def test_an_empty_path_set_is_unknown_not_trivially_leased(calls) -> None:
    """Samme regel som tomt landingssett på steg 11: fravær av data er ikke et
    positivt funn. Et tomt sett kan ikke være en delmengde av noe."""
    outcome = la.claim([])
    assert outcome.ok is False
    assert "tomt sett" in outcome.reason
    assert calls == [], "et tomt claim skal ikke engang spørre autoriteten"


def test_a_missing_token_never_reports_a_lease_as_taken(monkeypatch, calls) -> None:
    """FELLE 4, skrivesiden. Produsenten eier token-fila, så `chmod 0644` slår av
    verifiseringen. Feiler dette INN i «tatt», er kontrollen en bryter den
    kontrollerte parten selv kan skru av."""
    monkeypatch.delenv("SURFACE_RECEIPT_TOKEN", raising=False)
    monkeypatch.setattr(la, "_TOKEN_FILE", "/nonexistent/.surface_receipt_token")
    outcome = la.claim(["a.py"])
    assert outcome.ok is False
    assert outcome.acquired == ()
    assert "IKKE tatt" in outcome.reason
    assert calls == []


def test_an_unreachable_authority_never_reports_a_lease_as_taken(calls) -> None:
    calls.replies.append(OSError("connection refused"))
    outcome = la.claim(["a.py"])
    assert outcome.ok is False
    assert outcome.acquired == ()
    assert "UKJENT" in outcome.reason


def test_a_transport_failure_does_not_speculatively_release(calls) -> None:
    """Bevisst IKKE kompensert: ved transportfeil vet vi ikke om serveren rakk å
    skrive, og `release` er destruktiv for en søsken-kjøring med samme prinsipal
    (eieren er per prinsipal, ikke per kjøring). Vi rapporterer ukjent framfor å
    handle uten grunnlag."""
    calls.replies.append(TimeoutError("timed out"))
    outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is False
    assert len(calls) == 1, "ingen kompenserende release ved ukjent utfall"
    assert "UKJENT" in outcome.reason


# ---------------------------------------------------------------- suksess


def test_a_full_claim_reports_the_authoritys_set_not_the_requested_one(calls) -> None:
    """Kontrakten nedstrøms. Steg 11 sammenligner landingssettet mot DETTE settet,
    så det må komme fra autoriteten. En liste vi selv fant på ville gjenopprettet
    nøyaktig påstanden steg 6 fjerner."""
    calls.replies.append(_Resp(200, {"acquired": ["b.py", "a.py"],
                                     "owner": "surface:hermes-15"}))
    outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is True
    # IKKE sortert: autoriteten svarte i motsatt rekkefølge av det vi spurte om,
    # så likhet her beviser at settet kom DERFRA og ikke fra forespørselen vår.
    assert outcome.acquired == ("b.py", "a.py")
    assert outcome.owner == "surface:hermes-15"
    assert outcome.lease_set == outcome.acquired


def test_the_lease_set_is_empty_unless_the_claim_succeeded(calls) -> None:
    """`lease_set` er det steg 11 får lov til å lande innenfor. Et mislykket steg 6
    må gi et TOMT sett — og `LandingScopeGate` blokkerer på tomt lease-sett, så
    kjeden stopper i stedet for å lande fritt."""
    calls.replies.append(_Resp(500, {}))
    outcome = la.claim(["a.py"])
    assert outcome.ok is False
    assert outcome.lease_set == ()


def test_the_default_ttl_covers_reviewer_rounds(calls) -> None:
    """CLAUDE.md: default 1800s utløper midt i jobben og gjør commiten
    uattribuerbar. Steg 6 sitter per definisjon foran steg 10."""
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    la.claim(["a.py"])
    assert _body(calls[0])["ttl"] == 3600
    assert la.DEFAULT_TTL == 3600


def test_the_client_never_offers_an_owner_or_session_field(calls) -> None:
    """FELLE 2. `surface:` er reservert i `work_lease._session_id()` nettopp fordi
    en kaller-oppgitt eier er forfalskbar. Tilbyr klienten et slikt felt, er
    reservasjonen igjen en konvensjon og ikke et navnerom."""
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    la.claim(["a.py"], note="BL-4059")
    sent = _body(calls[0])
    assert set(sent) == {"paths", "ttl", "note"}
    assert not any("owner" in k or "session" in k for k in sent)
    assert calls[0].get_header("X-surface-token") == "test-token"


# ---------------------------------------------------------------- delvis


def test_a_partial_200_is_not_a_lease_and_is_compensated(calls) -> None:
    """FELLE 1+3. `work_lease.claim()` returnerer en EXIT-KODE, ikke
    `(ok, broke, blocked)` — så en 200 alene sier ingenting om hva som ble tatt.
    Leser vi `acquired` og finner et ufullstendig sett, er de vi FIKK allerede
    tatt: uten kompensasjon står de foreldreløse til TTL."""
    calls.replies.append(_Resp(200, {"acquired": ["a.py"], "owner": "surface:hermes-15"}))
    calls.replies.append(_Resp(200, {"artifact": "surface-lease-release-v1"}))
    outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is False
    assert outcome.acquired == ()
    assert "b.py" in outcome.reason
    assert outcome.still_held == ()
    assert len(calls) == 2, "det som faktisk ble tatt må slippes igjen"
    assert calls[1].full_url.endswith("/surface/lease/release")
    assert _body(calls[1])["paths"] == ["a.py"]


def test_a_partial_200_whose_compensation_fails_reports_STILL_HELD_loudly(
        calls, caplog) -> None:
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    calls.replies.append(OSError("release failed"))
    with caplog.at_level(logging.ERROR):
        outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is False
    assert outcome.still_held == ("a.py",)
    assert "STILL_HELD" in caplog.text


def test_a_5xx_is_an_unknown_outcome_not_a_refusal(calls, caplog) -> None:
    """Autoritetens 502 bærer samme tvetydighet som en transportfeil, og den er
    lesbar i ruten: `_claim` SKRIVER leasene, tilbakelesingen ligger i samme
    try-blokk, og feiler den svarer ruten 502 UTEN kompenseringen dens egen
    409-sti gjør. Å kalle det «leasen er IKKE tatt» ville vært en påstand uten
    grunnlag — samme form som hele dette arbeidet handler om."""
    calls.replies.append(_http_error(502, {"detail": "lease-kallet feilet (ref abc)"}))
    with caplog.at_level(logging.ERROR):
        outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is False
    assert "UKJENT" in outcome.reason
    assert "IKKE tatt" not in outcome.reason
    assert "foreldreløs" in caplog.text
    assert len(calls) == 1, "ingen spekulativ release på et ukjent utfall"


def test_a_4xx_that_is_not_409_is_a_plain_refusal(calls, caplog) -> None:
    """422 og 401 er entydige: serveren avviste før den skrev noe."""
    calls.replies.append(_http_error(401, {"detail": "ukjent token"}))
    with caplog.at_level(logging.ERROR):
        outcome = la.claim(["a.py"])
    assert outcome.ok is False
    assert "IKKE tatt" in outcome.reason
    assert caplog.text == ""


def test_more_paths_than_the_authority_accepts_fails_diagnosably(calls) -> None:
    """Over 50 stier ga «autoriteten svarte 422» — fail-closed, men umulig å
    diagnostisere, og permanent. Vi deler heller ikke opp: et oppdelt claim er
    ikke atomisk, og et delvis resultat på tvers av bolker er den foreldreløse
    tilstanden igjen."""
    outcome = la.claim([f"f{i}.py" for i in range(51)])
    assert outcome.ok is False
    assert "51" in outcome.reason and "50" in outcome.reason
    assert calls == []


def test_a_409_carries_still_held_and_names_the_blocking_holder(calls, caplog) -> None:
    """Serveren kompenserer på sin egen 409-sti. Klarer den det ikke, er
    `STILL_HELD` den ENESTE opplysningen som betyr noe — og den må være umulig å
    overse, ellers har vi byttet en stille foreldreløs lease mot en litt mindre
    stille."""
    calls.replies.append(_http_error(409, {"detail": {
        "reason": "kunne ikke ta hele settet",
        "blocked": [{"path": "b.py", "holder": "surface:annen"}],
        "rolled_back": [], "STILL_HELD": ["a.py"], "ref": "abc123"}}))
    with caplog.at_level(logging.ERROR):
        outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is False
    assert outcome.acquired == ()
    assert outcome.still_held == ("a.py",)
    assert outcome.blocked_by == (("b.py", "surface:annen"),)
    assert outcome.ref == "abc123"
    assert "STILL_HELD" in outcome.reason
    assert "a.py" in caplog.text


def test_a_409_names_the_paths_no_lease_was_written_for(calls) -> None:
    """Serveren oppgir `no_lease_written` eksplisitt. Kastet vi den, sto
    operatøren igjen med «ingen grunn oppgitt» på et avslag serveren nettopp
    forklarte."""
    calls.replies.append(_http_error(409, {"detail": {
        "blocked": [], "no_lease_written": ["c.py"], "rolled_back": ["a.py"],
        "STILL_HELD": [], "ref": "xyz"}}))
    outcome = la.claim(["a.py", "c.py"])
    assert outcome.ok is False
    assert "c.py" in outcome.reason
    assert "ingen grunn oppgitt" not in outcome.reason


def test_a_409_that_rolled_back_cleanly_is_a_plain_refusal(calls, caplog) -> None:
    calls.replies.append(_http_error(409, {"detail": {
        "blocked": [{"path": "a.py", "holder": "surface:annen"}],
        "rolled_back": ["b.py"], "STILL_HELD": [], "ref": "def456"}}))
    with caplog.at_level(logging.ERROR):
        outcome = la.claim(["a.py", "b.py"])
    assert outcome.ok is False
    assert outcome.still_held == ()
    assert "surface:annen" in outcome.reason
    assert "STILL_HELD" not in caplog.text


# ---------------------------------------------------------------- livssyklus


def test_held_lease_releases_exactly_what_it_took(calls) -> None:
    calls.replies.append(_Resp(200, {"acquired": ["a.py", "b.py"]}))
    calls.replies.append(_Resp(200, {}))
    with la.held_lease(["a.py", "b.py"]) as outcome:
        assert outcome.ok is True
    assert len(calls) == 2
    assert calls[1].full_url.endswith("/surface/lease/release")
    assert sorted(_body(calls[1])["paths"]) == ["a.py", "b.py"]


def test_held_lease_releases_even_when_the_body_raises(calls) -> None:
    """En lease som bare slippes på den glade stien er ikke sluppet."""
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    calls.replies.append(_Resp(200, {}))
    with pytest.raises(RuntimeError):
        with la.held_lease(["a.py"]):
            raise RuntimeError("bygget feilet")
    assert len(calls) == 2
    assert calls[1].full_url.endswith("/surface/lease/release")


def test_held_lease_does_not_release_what_it_never_took(calls) -> None:
    calls.replies.append(_http_error(409, {"detail": {"blocked": [], "STILL_HELD": []}}))
    with la.held_lease(["a.py"]) as outcome:
        assert outcome.ok is False
    assert len(calls) == 1, "ingenting ble tatt, så ingenting skal slippes"


def test_held_lease_is_loud_when_the_release_fails(calls, caplog) -> None:
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    calls.replies.append(OSError("network gone"))
    with caplog.at_level(logging.ERROR):
        with la.held_lease(["a.py"]) as hold:
            assert hold.ok is True
    assert "release FEILET" in caplog.text


def test_a_failed_release_is_readable_and_not_only_logged(calls) -> None:
    """`LeaseOutcome` er frossen og alt gitt fra seg når slippet skjer, så uten
    dette ville en steg-6-kvittering stått med ok=True og ingen spor av at leasen
    aldri kom tilbake."""
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    calls.replies.append(OSError("network gone"))
    with la.held_lease(["a.py"]) as hold:
        pass
    assert hold.release_failed
    assert hold.ok is True, "leasen BLE tatt — det er slippet som feilet"


def test_a_clean_release_leaves_no_failure_mark(calls) -> None:
    calls.replies.append(_Resp(200, {"acquired": ["a.py"]}))
    calls.replies.append(_Resp(200, {}))
    with la.held_lease(["a.py"]) as hold:
        pass
    assert hold.release_failed == ""


def test_held_lease_blocks_rather_than_raising(calls) -> None:
    """Steg 6 er en gate. En gate som feiler skal gi en begrunnet BLOCK oppover i
    kjeden, ikke et unntak `GovernedCodeRunner` fanger som «runner exception» —
    da mister blokkeringen sin årsak."""
    calls.replies.append(OSError("down"))
    with la.held_lease(["a.py"]) as outcome:
        assert outcome.ok is False
        assert outcome.reason


# ---------------------------------------------------------------- lesesiden


def test_check_reports_unverified_as_none_not_false(calls, monkeypatch) -> None:
    """`None` er en tredje verdi med vilje: `False` ville sagt «ingen lease
    finnes», som er en påstand vi ikke har grunnlag for når vi ikke fikk spurt."""
    monkeypatch.delenv("SURFACE_RECEIPT_TOKEN", raising=False)
    monkeypatch.setattr(la, "_TOKEN_FILE", "/nonexistent/token")
    clear, note = la.check(["a.py"])
    assert clear is None
    assert "UVERIFISERT" in note


def test_check_reports_an_authority_outage_as_none_not_clear(calls) -> None:
    """Den LEVENDE lesestien: `faber_observe._resolve_lease_clear` returnerer
    `verified` ordrett når den ikke er `None`. Ble en utilgjengelig autoritet til
    `True` her, ville et autoritets-utfall blitt et grønt lys på steg 4 — gaten
    passert uten at noen lease finnes."""
    calls.replies.append(OSError("connection refused"))
    clear, note = la.check(["a.py"])
    assert clear is None
    assert "UVERIFISERT" in note


def test_check_reports_a_non_200_as_none_not_clear(calls) -> None:
    calls.replies.append(_Resp(503, {}))
    clear, note = la.check(["a.py"])
    assert clear is None
    assert "UVERIFISERT" in note


def test_check_reads_lease_clear_from_the_authority(calls) -> None:
    calls.replies.append(_Resp(200, {"lease_clear": True, "held_by_me": ["a.py"],
                                     "held_by_others": []}))
    clear, note = la.check(["a.py"])
    assert clear is True
    assert "1 av 1 eid" in note


# ---------------------------------------------------------- kreditivet

# Modus- og eierkontrollen er en HERDINGSKONTROLL som ble den billigste bryteren
# for å skru verifiseringen AV: produsenten eier fila, så `chmod 0644` ga tom token.
# Etter BL-4059 leser BÅDE check og claim dette ene stedet, så kontrollens
# rekkevidde er doblet. Den var utestet da den flyttet — det er den ikke nå.


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SURFACE_RECEIPT_TOKEN", raising=False)
    f = tmp_path / ".surface_receipt_token"
    f.write_text("hemmelig", encoding="utf-8")
    monkeypatch.setattr(la, "_TOKEN_FILE", str(f))
    return f


def test_a_correctly_hardened_token_file_is_read(token_file) -> None:
    token_file.chmod(0o600)
    assert la.surface_token() == "hemmelig"


def test_a_world_readable_token_file_yields_no_token(token_file) -> None:
    """0644 er nøyaktig bryteren produsenten kan bruke på seg selv."""
    token_file.chmod(0o644)
    assert la.surface_token() == ""


def test_a_group_readable_token_file_yields_no_token(token_file) -> None:
    token_file.chmod(0o640)
    assert la.surface_token() == ""


def test_a_symlinked_token_file_yields_no_token(tmp_path, monkeypatch) -> None:
    """En symlink flytter hvem som egentlig eier og verner innholdet."""
    monkeypatch.delenv("SURFACE_RECEIPT_TOKEN", raising=False)
    real = tmp_path / "real"
    real.write_text("hemmelig", encoding="utf-8")
    real.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setattr(la, "_TOKEN_FILE", str(link))
    assert la.surface_token() == ""


def test_the_env_token_is_for_tests_and_wins(token_file, monkeypatch) -> None:
    token_file.chmod(0o644)
    monkeypatch.setenv("SURFACE_RECEIPT_TOKEN", "fra-env")
    assert la.surface_token() == "fra-env"


def test_scope_paths_matches_what_the_check_route_is_asked_about() -> None:
    """`check` og `claim` MÅ se samme sett. Er de uenige om hva som er i scope,
    verifiserer vi én mengde og leaser en annen.

    BL-4070 (D2) UTVIDET SETTET, og grunnen over står uendret — den er nettopp
    hvorfor utvidelsen måtte skje HER og ikke hos kalleren. Det fantes to
    parsere: denne leste kun `.py`, mens `faber_control_bridge._paths_from_scope`
    leste ti filformer. Samme streng ga altså to filer hos den ene og «scope
    navngir ingen filer» hos den andre, og steg 6 rapporterte det siste som et
    SVAR om leasen. Autoriteten selv har aldri hatt noen filtype-begrensning —
    den holder lease på hva som helst — så `.py`-filteret utelukket ikke noe
    autoriteten ikke kunne svare på; det gjorde bare spørsmålet ustillbart.

    Broen delegerer nå hit, og `faber_observe` importerte allerede denne
    funksjonen (BL-4059). Det finnes ÉN parser, så de kan ikke divergere igjen.
    """
    assert la.scope_paths("hermes-agent: a.py, b.py") == ["a.py", "b.py"]
    assert la.scope_paths("hermes-agent: a.py, notes.md") == ["a.py", "notes.md"]
    assert la.scope_paths("hermes-agent: hermes-dashboard.service") == [
        "hermes-dashboard.service"]
    # Utvidelsen er en LISTE, ikke «alt»: en vilkårlig setning er fortsatt ikke
    # en filsti, ellers ville scope-lesingen blitt sin egen kontroll-som-ikke-
    # kan-feile.
    assert la.scope_paths("hermes-agent: se ADR-061 for detaljer") == []


def test_the_bridge_and_the_authority_cannot_disagree_about_a_scope() -> None:
    """D2 som regresjon: to parsere for én grense er samme feilform som to
    kilder for ett lease-sett."""
    from agent.faber_control_bridge import _paths_from_scope

    for scope in ("hermes-agent: a.py, notes.md, unit.service",
                  "hermes-agent: agent/x.py",
                  "hermes-agent: ingenting her",
                  ""):
        assert list(la.scope_paths(scope)) == list(_paths_from_scope(scope)), scope
