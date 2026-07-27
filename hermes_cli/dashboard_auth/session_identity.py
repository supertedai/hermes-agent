"""Sesjons-identitet for multiuser-recall (BL-2790, BL-2466/WP2).

Gatewayen (tui_gateway ``prompt.submit``) registrerer HVEM som sendte turnen:
sid → brukernavn, stemplet av den autentiserte frontend-proxyen på .14
(butikk-login + TOTP). Tool-laget leser den tilbake via ``session_id``-kwargen
som registry.dispatch allerede sender inn i hver handler — også når turnen
kjører i en ANNEN prosess (compute-host-isolasjon). Derfor fil i HERMES_HOME
(samme hjem som ``users.json``), ikke in-proc map.

Kontrakt (samme som server-siden BL-2783/2786/2789):
- Fravær av oppføring = legacy/admin-æra (Morten konsoll/PTY/dashboard-token)
  → ``get_identity`` returnerer None og nedstrøms bruker eier-default.
- Les-feil skiller REN MISS (None) fra KORRUPT infrastruktur (exception) slik
  at tool-gaten kan feile LUKKET for identifiserte sesjoner uten å straffe
  legacy-stier, og recall-verktøyene feiler høyt i stedet for å falle til eier.
- Brukernavn normaliseres (strip/lower) — skrivesiden på .12 matcher eksakt.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from .user_store import get_user, store_path

_LOCK = threading.Lock()
_MAX_ENTRIES = 500
_MAX_AGE_S = 7 * 24 * 3600


def identity_path() -> Path:
    """``HERMES_HOME/session_identity.json`` — samme hjem som users-butikken."""
    return store_path().parent / "session_identity.json"


def _load() -> dict:
    """Rå lesing. IO-/parse-feil PROPAGERER — leserne skal feile lukket."""
    p = identity_path()
    if not p.exists():
        return {}
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("session_identity.json: toppnivå må være objekt")
    return data


def set_identity(session_id: str, user_id: str) -> None:
    """Registrer sid→bruker. Kalles av gatewayen ved prompt.submit.

    Reparerer korrupt fil (skriveren er eneste vei tilbake til frisk
    tilstand; leserne feiler lukket inntil da). Atomisk skriv + 0600.
    """
    sid = (session_id or "").strip()
    uid = (user_id or "").strip().lower()
    if not sid or not uid:
        raise ValueError("session_id og user_id kreves")
    with _LOCK:
        try:
            data = _load()
        except Exception:
            data = {}
        now = time.time()
        data[sid] = {"user_id": uid, "ts": now}
        data = {
            k: v for k, v in data.items()
            if isinstance(v, dict) and now - float(v.get("ts", 0) or 0) <= _MAX_AGE_S
        }
        if len(data) > _MAX_ENTRIES:
            oldest = sorted(data.items(), key=lambda kv: kv[1].get("ts", 0))
            for k, _ in oldest[: len(data) - _MAX_ENTRIES]:
                data.pop(k, None)
        p = identity_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".sessid-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def get_identity(session_id: str) -> Optional[str]:
    """Innsenderen av turnene i sesjonen, eller None ved REN miss (legacy).

    Korrupt fil → exception (fail-lukket hos kalleren, se modul-docstring).
    """
    sid = (session_id or "").strip()
    if not sid:
        return None
    with _LOCK:
        data = _load()
    ent = data.get(sid)
    if not isinstance(ent, dict):
        return None
    uid = str(ent.get("user_id") or "").strip().lower()
    return uid or None


def resolve_role(user_id: str) -> str:
    """Server-side rolle fra users-butikken — ALDRI klient-assertert.

    Ukjent bruker, disabled bruker eller oppslagsfeil → "user" (restriktiv).
    """
    try:
        u = get_user((user_id or "").strip().lower())
    except Exception:
        return "user"
    if not u or u.get("disabled"):
        return "user"
    return "admin" if u.get("role") == "admin" else "user"
