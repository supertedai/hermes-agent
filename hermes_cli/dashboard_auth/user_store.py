"""Lokal flerbruker-butikk for Symbiose chat-plattformen (BL-2653).

Fundamentet for multiuser-planen (BL-2466 Phase 3 / charter
``plan:symbiose_multiuser_chat_platform``): en liten, filbasert
bruker-registrering som BÅDE auth-provideren
(``plugins/dashboard_auth/local_users``) og admin-API-et
(``plugins/brukere/dashboard/plugin_api.py``) deler. Lever i
``hermes_cli.dashboard_auth`` fordi plugin-API-filer lastes som
frittstående moduler (``plugins/`` er ikke importerbar pakkevei for
undermappene) mens ``hermes_cli`` alltid er importerbar.

Designvalg:
  * **JSON-fil i HERMES_HOME** (``users.json``, 0600) — null infrastruktur,
    samme sone som resten av GUI-tilstanden (utenfor batch-jailene, som
    bevisst har egen HERMES_HOME).
  * **scrypt-hash** (stdlib) i nøyaktig samme format som
    ``plugins/dashboard_auth/basic`` (``scrypt$n$r$p$salt$dk``) så hasher
    er kompatible på tvers.
  * **Signeringssecret bor i butikken** — genereres ved opprettelse, så
    cookie-sesjoner overlever restart uten egen konfigurasjon.
  * **Ingen sletting.** Brukere deaktiveres (``disabled=True``) — aldri
    fjernes (husets «vi sletter ingenting»-regel). Deaktivering dreper
    også levende sesjoner fordi provideren slår opp brukeren per verify.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

# Samme scrypt-parametre som plugins/dashboard_auth/basic (interaktiv
# innlogging, ~16 MiB). Formatet er identisk så hasher kan flyttes.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,31}$")
ROLES = ("admin", "user")

_LOCK = threading.Lock()


def store_path() -> Path:
    """``HERMES_HOME/users.json`` — samme hjem som resten av GUI-tilstanden."""
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "users.json"


# ---------------------------------------------------------------------------
# Hashing (delt format med dashboard_auth/basic)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SCRYPT_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN, maxmem=0,
    )
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    """Konstant-tid scrypt-verify; False på ethvert malformt hash-format."""
    try:
        scheme, n_s, r_s, p_s, salt_b64, dk_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt,
            n=n, r=r, p=p, dklen=len(expected), maxmem=0,
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


# Dummy-hash så ukjent brukernavn koster ~like mye som feil passord
# (ingen timing-orakel for brukernavn-enumerering).
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-verify")


# ---------------------------------------------------------------------------
# Butikk-I/O
# ---------------------------------------------------------------------------


def _empty_store() -> dict:
    return {"version": 1, "secret": "", "users": []}


def load_store(path: Optional[Path] = None) -> dict:
    p = path or store_path()
    try:
        data = json.loads(p.read_text())
    except FileNotFoundError:
        return _empty_store()
    except (OSError, ValueError):
        # Korrupt/uleselig fil skal aldri åpne en innloggingsvei —
        # behandles som tom (fail-lukket: ingen brukere = provider hopper av).
        return _empty_store()
    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        return _empty_store()
    return data


def save_store(store: dict, path: Optional[Path] = None) -> None:
    """Atomisk skriv (tempfil + rename), 0600, i samme katalog."""
    p = path or store_path()
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".users-")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(store, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def signing_secret(store: dict) -> bytes:
    """Token-signeringsnøkkelen (base64 i butikken); tom => ingen sesjoner."""
    raw = str(store.get("secret") or "")
    try:
        decoded = base64.b64decode(raw)
        if len(decoded) >= 16:
            return decoded
    except (ValueError, TypeError):
        pass
    return b""


# ---------------------------------------------------------------------------
# Bruker-operasjoner (alle tar/returnerer public dicts uten hash)
# ---------------------------------------------------------------------------


def _public(u: dict) -> dict:
    return {
        "username": u.get("username", ""),
        "display_name": u.get("display_name", ""),
        "email": u.get("email", ""),
        "role": u.get("role", "user"),
        "disabled": bool(u.get("disabled", False)),
        "created_at": u.get("created_at", ""),
        "created_by": u.get("created_by", ""),
        "last_login": u.get("last_login", ""),
    }


def list_users(path: Optional[Path] = None) -> list[dict]:
    return [_public(u) for u in load_store(path).get("users", [])]


def get_user(username: str, path: Optional[Path] = None) -> Optional[dict]:
    for u in load_store(path).get("users", []):
        if u.get("username") == username:
            return dict(u)
    return None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def create_user(
    *,
    username: str,
    password: str,
    display_name: str = "",
    email: str = "",
    role: str = "user",
    created_by: str = "",
    path: Optional[Path] = None,
) -> dict:
    """Opprett bruker. Første bruker i en tom butikk MÅ være admin
    (bootstrap — «jeg som første og eneste bruker»), og genererer
    samtidig signeringssecreten."""
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError(
            f"ugyldig brukernavn {username!r} (krav: {USERNAME_RE.pattern})"
        )
    if role not in ROLES:
        raise ValueError(f"ugyldig rolle {role!r} (tillatt: {ROLES})")
    if not password or len(password) < 8:
        raise ValueError("passord må være minst 8 tegn")
    with _LOCK:
        store = load_store(path)
        if any(u.get("username") == username for u in store["users"]):
            raise ValueError(f"brukernavn finnes allerede: {username}")
        if not store["users"]:
            role = "admin"  # bootstrap: første bruker er alltid admin
        if not store.get("secret"):
            store["secret"] = base64.b64encode(secrets.token_bytes(32)).decode()
        user = {
            "username": username,
            "display_name": (display_name or "").strip() or username,
            "email": (email or "").strip(),
            "role": role,
            "password_hash": hash_password(password),
            "disabled": False,
            "created_at": _now(),
            "created_by": created_by,
            "last_login": "",
        }
        store["users"].append(user)
        save_store(store, path)
    return _public(user)


def update_user(
    username: str,
    *,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    disabled: Optional[bool] = None,
    path: Optional[Path] = None,
) -> dict:
    with _LOCK:
        store = load_store(path)
        target = None
        for u in store["users"]:
            if u.get("username") == username:
                target = u
                break
        if target is None:
            raise KeyError(f"ukjent bruker: {username}")
        if role is not None:
            if role not in ROLES:
                raise ValueError(f"ugyldig rolle {role!r}")
            if (
                target.get("role") == "admin"
                and role != "admin"
                and sum(
                    1
                    for u in store["users"]
                    if u.get("role") == "admin" and not u.get("disabled")
                ) <= 1
            ):
                raise ValueError("kan ikke fjerne siste aktive admin-rolle")
            target["role"] = role
        if disabled is not None:
            if (
                disabled
                and target.get("role") == "admin"
                and sum(
                    1
                    for u in store["users"]
                    if u.get("role") == "admin" and not u.get("disabled")
                ) <= 1
            ):
                raise ValueError("kan ikke deaktivere siste aktive admin")
            target["disabled"] = bool(disabled)
        if display_name is not None:
            target["display_name"] = display_name.strip() or target["username"]
        if email is not None:
            target["email"] = email.strip()
        save_store(store, path)
        return _public(target)


def set_password(username: str, password: str, path: Optional[Path] = None) -> None:
    if not password or len(password) < 8:
        raise ValueError("passord må være minst 8 tegn")
    with _LOCK:
        store = load_store(path)
        for u in store["users"]:
            if u.get("username") == username:
                u["password_hash"] = hash_password(password)
                save_store(store, path)
                return
    raise KeyError(f"ukjent bruker: {username}")


def check_login(username: str, password: str, path: Optional[Path] = None) -> Optional[dict]:
    """Konstant-tid innloggingssjekk.

    Returnerer public bruker-dict ved suksess, ellers ``None`` — skiller
    aldri «ukjent bruker» fra «feil passord» (verken i svar eller timing).
    Deaktiverte brukere feiler som om passordet var feil. Stempler
    ``last_login`` ved suksess.
    """
    username = (username or "").strip().lower()
    with _LOCK:
        store = load_store(path)
        target = None
        for u in store["users"]:
            if hmac.compare_digest(
                str(u.get("username", "")).encode(), username.encode()
            ):
                target = u
        target_hash = (
            str(target.get("password_hash", "")) if target else _DUMMY_HASH
        ) or _DUMMY_HASH
        ok = verify_password(password, target_hash)
        if not (ok and target is not None and not target.get("disabled")):
            return None
        target["last_login"] = _now()
        save_store(store, path)
        return _public(target)


def generate_password(length: int = 16) -> str:
    """Lesbart engangspassord (4-tegns segmenter à ~23 bits, ``length`` ≈
    antall tellende tegn — reviewer-funn M2: parameteren skal virke)."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    segments = max(3, (max(8, int(length)) + 3) // 4)
    return "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(segments)
    )
