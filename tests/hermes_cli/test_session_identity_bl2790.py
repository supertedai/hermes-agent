"""BL-2790 (BL-2466/WP2): sesjons-identitet, rolle-gate og reserverte navn.

Kontraktene som testes speiler server-siden (BL-2783/2786/2789):
ren miss = legacy → eier-default; korrupt infra = fail-LUKKET;
rolle slås opp server-side; reserverte sentinel-navn kan aldri bli brukere.
"""
import json

import pytest

from hermes_cli.dashboard_auth import session_identity as si
from hermes_cli.dashboard_auth import user_store


@pytest.fixture()
def ident_file(tmp_path, monkeypatch):
    p = tmp_path / "session_identity.json"
    monkeypatch.setattr(si, "identity_path", lambda: p)
    return p


def test_roundtrip_normaliserer(ident_file):
    si.set_identity("sid-1", "  TestBruker ")
    assert si.get_identity("sid-1") == "testbruker"


def test_ren_miss_er_none(ident_file):
    assert si.get_identity("finnes-ikke") is None
    assert si.get_identity("") is None


def test_korrupt_fil_raiser_og_set_reparerer(ident_file):
    ident_file.write_text("{korrupt", encoding="utf-8")
    with pytest.raises(Exception):
        si.get_identity("sid-1")
    si.set_identity("sid-1", "anna")  # skriveren er veien tilbake til frisk fil
    assert si.get_identity("sid-1") == "anna"


def test_gammel_oppfoering_prunes(ident_file):
    si.set_identity("sid-gammel", "anna")
    data = json.loads(ident_file.read_text(encoding="utf-8"))
    data["sid-gammel"]["ts"] = 1.0  # eldgammel → skal prunes ved neste skriv
    ident_file.write_text(json.dumps(data), encoding="utf-8")
    si.set_identity("sid-ny", "anna")
    assert si.get_identity("sid-gammel") is None
    assert si.get_identity("sid-ny") == "anna"


@pytest.mark.parametrize("navn", sorted(user_store.RESERVED_USERNAMES))
def test_reserverte_brukernavn_nektes(tmp_path, navn):
    path = tmp_path / "users.json"
    user_store.create_user(username="eier", password="hemmelig123", path=path)
    with pytest.raises(ValueError, match="reservert"):
        user_store.create_user(username=navn, password="hemmelig123", path=path)


def test_resolve_role_server_side(monkeypatch):
    def fake_get_user(u, path=None):
        return {
            "sjef": {"role": "admin", "disabled": False},
            "vanlig": {"role": "user", "disabled": False},
            "sperret": {"role": "admin", "disabled": True},
        }.get(u)

    monkeypatch.setattr(si, "get_user", fake_get_user)
    assert si.resolve_role("sjef") == "admin"
    assert si.resolve_role("SJEF ") == "admin"  # normaliseres
    assert si.resolve_role("vanlig") == "user"
    assert si.resolve_role("ukjent") == "user"
    assert si.resolve_role("sperret") == "user"  # disabled admin = restriktiv


def test_rolle_gate(monkeypatch):
    import model_tools

    # legacy (ren miss) → urørt full flate
    monkeypatch.setattr(si, "get_identity", lambda sid: None)
    assert model_tools._symbiose_role_gate("execute_code", "sid") is None

    # identifisert ikke-admin → default-deny utenfor allowlisten
    monkeypatch.setattr(si, "get_identity", lambda sid: "anna")
    monkeypatch.setattr(si, "resolve_role", lambda u: "user")
    deny = model_tools._symbiose_role_gate("execute_code", "sid")
    assert deny is not None
    assert json.loads(deny)["error_type"] == "tool_denied_role"
    assert model_tools._symbiose_role_gate("symbiose_ask", "sid") is None
    assert model_tools._symbiose_role_gate("qdrant_search", "sid") is None

    # admin (server-side rolle) → urørt
    monkeypatch.setattr(si, "resolve_role", lambda u: "admin")
    assert model_tools._symbiose_role_gate("execute_code", "sid") is None

    # korrupt identitets-infra → fail-LUKKET med egen feiltype
    def _boom(sid):
        raise RuntimeError("korrupt fil")

    monkeypatch.setattr(si, "get_identity", _boom)
    deny = model_tools._symbiose_role_gate("graph_query", "sid")
    assert deny is not None
    assert json.loads(deny)["error_type"] == "identity_infra_error"
