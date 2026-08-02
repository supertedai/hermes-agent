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

# BL-2790 (Reviewer-mandat BL-2789, A7-dimensjon): identitets-sentineler og
# aliaser som server-siden (.12) klassifiserer som EIER-trafikk. En bruker med
# et slikt navn ville fått Mortens recall — derfor kan de ALDRI opprettes.
# ("morten" selv er vernet av unikhets-sjekken; migreringsveien skapte ham.)
# Kilde-speil av .12 apis/unified_api/peruser_access.py RESERVED_USERNAMES_CONTRACT
# (drift-vakt: AGI tests/test_owner_alias_reserved_sync.py). ALT som en .12-sti
# kollapser til eier-prinsipalen MAA bannes her, ellers faar navnet Mortens recall.
RESERVED_USERNAMES = frozenset({
    "system", "anonymous", "default-user", "morpheus",       # dispatcher-sentineler + morpheus-alias
    "claude", "assistant", "chatgpt", "session", "default",  # gateway reserved_session_ids (-> DEFAULT_CANONICAL_USER_ID)
})

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
        "has_totp": bool(u.get("totp_secret")),
        # BL-3404: godkjent søker som ennå ikke har skannet inn authenticator.
        # Kontoen finnes, men gaten slipper den KUN inn i innrullerings-steget.
        "totp_pending": bool(u.get("totp_pending_secret")) and not u.get("totp_secret"),
    }


def list_users(path: Optional[Path] = None) -> list[dict]:
    return [_public(u) for u in load_store(path).get("users", [])]


def get_user(username: str, path: Optional[Path] = None) -> Optional[dict]:
    for u in load_store(path).get("users", []):
        if u.get("username") == username:
            return dict(u)
    return None


def get_public_user(username: str, path: Optional[Path] = None) -> Optional[dict]:
    """Som :func:`get_user`, men uten hash/secret — trygg å returnere ut."""
    u = get_user(username, path)
    return _public(u) if u else None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def create_user(
    *,
    username: str,
    password: str = "",
    password_hash: str = "",
    display_name: str = "",
    email: str = "",
    role: str = "user",
    created_by: str = "",
    totp: bool = False,
    totp_secret: str = "",
    totp_pending: bool = False,
    path: Optional[Path] = None,
) -> dict:
    """Opprett bruker. Første bruker i en tom butikk MÅ være admin
    (bootstrap — «jeg som første og eneste bruker»), og genererer
    samtidig signeringssecreten. ``totp=True`` genererer 2FA-secret
    (``totp_secret`` kan overstyre — migreringsveien fra .auth.json);
    secreten returneres da ÉN gang i feltet ``totp_secret``.

    BL-3404 (selvregistrering): ``password_hash`` lar godkjenningsveien
    gjenbruke hashen som ble laget da søkeren fylte skjemaet — klartekst-
    passordet forlot aldri den ene requesten. ``totp_pending=True`` legger
    secreten i ``totp_pending_secret`` og returnerer den ALDRI: den skal
    til brukerens egen authenticator ved første innlogging, ikke til
    admin-flaten (én hemmelighet, én mottaker)."""
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError(
            f"ugyldig brukernavn {username!r} (krav: {USERNAME_RE.pattern})"
        )
    if username in RESERVED_USERNAMES:
        raise ValueError(
            f"reservert brukernavn: {username!r} (identitets-sentinel/alias — "
            "ville gitt eier-tilgang på Symbiose-siden, BL-2790)"
        )
    if role not in ROLES:
        raise ValueError(f"ugyldig rolle {role!r} (tillatt: {ROLES})")
    if password_hash:
        if not str(password_hash).startswith("scrypt$"):
            raise ValueError("ugyldig password_hash-format")
        stored_hash = str(password_hash)
    else:
        if not password or len(password) < 8:
            raise ValueError("passord må være minst 8 tegn")
        stored_hash = hash_password(password)
    secret_b32 = (totp_secret or "").strip() or (
        generate_totp_secret() if (totp or totp_pending) else ""
    )
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
            "password_hash": stored_hash,
            "disabled": False,
            "created_at": _now(),
            "created_by": created_by,
            "last_login": "",
        }
        if secret_b32:
            user["totp_pending_secret" if totp_pending else "totp_secret"] = secret_b32
        store["users"].append(user)
        save_store(store, path)
    out = _public(user)
    if secret_b32 and not totp_pending:
        out["totp_secret"] = secret_b32  # vises ÉN gang ved opprettelse
        out["otpauth_uri"] = otpauth_uri(username, secret_b32)
    return out


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


def check_login(username: str, password: str, path: Optional[Path] = None,
                stamp: bool = True) -> Optional[dict]:
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
        # ``stamp=False``: passordet stemte, men innloggingen er ikke ferdig
        # (BL-3404 innrullering står igjen). «Sist innlogget» skal fortelle om
        # fullførte innlogginger, ellers lyver admin-flaten.
        if stamp:
            target["last_login"] = _now()
            save_store(store, path)
        return _public(target)


def _totp_at(secret_b32: str, t: float, step: int = 30, digits: int = 6) -> str:
    """RFC 6238-kode for tidspunkt ``t`` — ren stdlib, samme algoritme som
    frontend-gatens setup_2fa (ai.byopus.com)."""
    import struct

    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper().replace(" ", "") + pad)
    h = hmac.new(key, struct.pack(">Q", int(t // step)), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str(
        (int.from_bytes(h[o:o + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    ).zfill(digits)


def check_totp(
    secret_b32: str, code: str, window: int = 1,
    at_time: Optional[float] = None,
) -> bool:
    """Konstant-tid TOTP-verify, ±``window`` steg (30 s) toleranse.

    ``at_time`` lar en PÅLITELIG caller (frontend-gaten på .14, som har
    NTP-riktig klokke) oppgi verifiseringstidspunktet — .15s egen klokke
    driver usynkronisert (chrony når ikke kildene gjennom brannmuren).
    Bindes av calleren til et smalt vindu rundt server-tid."""
    code = str(code or "").strip().replace(" ", "")
    if not (secret_b32 and code):
        return False
    now = at_time if at_time is not None else time.time()
    return any(
        hmac.compare_digest(_totp_at(secret_b32, now + w * 30), code)
        for w in range(-window, window + 1)
    )


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def otpauth_uri(username: str, secret_b32: str) -> str:
    import urllib.parse

    return (
        "otpauth://totp/Opus:%s?secret=%s&issuer=Opus&digits=6&period=30"
        % (urllib.parse.quote(username), secret_b32)
    )


def get_totp_secret(username: str, path: Optional[Path] = None) -> str:
    """KUN for verifisering server-side — aldri ut gjennom API-et."""
    u = get_user(username, path)
    return str((u or {}).get("totp_secret") or "")


def set_totp(
    username: str, secret_b32: Optional[str], path: Optional[Path] = None
) -> None:
    """Sett (eller fjern med ``None``) TOTP-secret for en bruker."""
    with _LOCK:
        store = load_store(path)
        for u in store["users"]:
            if u.get("username") == username:
                if secret_b32:
                    u["totp_secret"] = secret_b32
                else:
                    u.pop("totp_secret", None)
                # BL-3404 (reviewer-funn M4): en ventende innrullerings-secret
                # MÅ dø sammen med den ekte. Uten dette ville «2FA på» og så
                # «2FA av» på en godkjent-men-ikke-innrullert bruker vekket den
                # foreldreløse pending-secreten til live igjen — og kastet
                # brukeren inn i innrullering med en nøkkel ingen har.
                u.pop("totp_pending_secret", None)
                save_store(store, path)
                return
    raise KeyError(f"ukjent bruker: {username}")


def verify_login(
    username: str, password: str, code: str = "",
    at_time: Optional[float] = None, path: Optional[Path] = None,
) -> Optional[dict]:
    """Full innloggingssjekk for frontend-gaten: passord + (om satt) TOTP.

    Generisk feil — skiller aldri ukjent bruker / feil passord / feil kode.
    Har brukeren ``totp_secret`` er koden OBLIGATORISK. ``at_time`` — se
    :func:`check_totp` (klokke-skew-kompensasjon fra pålitelig gate).

    MERK (BL-3404, reviewer-funn): denne har i dag INGEN kallere — gaten
    bruker :func:`verify_login_ex` og provideren bruker :func:`check_login`.
    Den beholdes som et stabilt API, men den måtte lukkes for
    innrullerings-tilstanden: uten sjekken under ville en godkjent, ikke
    innrullert bruker sluppet gjennom her (ingen ``totp_secret`` ennå) den
    dagen noen wirer den opp igjen.
    """
    user = check_login(username, password, path, stamp=False)
    if user is None:
        return None
    if pending_totp_secret(user["username"], path):
        return None
    secret = get_totp_secret(user["username"], path)
    if secret and not check_totp(secret, code, at_time=at_time):
        return None
    _stamp_login(user["username"], path)   # kun ved FULLFØRT innlogging
    return user


def has_totp(username: str, path: Optional[Path] = None) -> bool:
    return bool(get_totp_secret(username, path))


# ---------------------------------------------------------------------------
# BL-3404: selvregistrering med admin-godkjenning
#
# Flyten, og hvorfor den ser slik ut:
#   1. Besøkende fyller skjemaet på ai.byopus.com. Gaten (.14) sender det
#      server-til-server hit over SAMME ssh-tunnel som login-check.
#   2. Passordet hashes HER, i requesten som bar det. Ingen klartekst når
#      noen gang disk, logg eller admin-flate.
#   3. Søknaden ligger som «open» til Morten godkjenner i /brukere.
#   4. Godkjenning oppretter brukeren med den lagrede hashen + en 2FA-secret
#      i ``totp_pending_secret``. Secreten returneres ALDRI til admin.
#   5. Brukeren logger inn første gang: gaten får «enroll»-svar (IKKE en
#      sesjon), viser secreten én gang, og krever en gyldig kode før kontoen
#      promoteres til ekte ``totp_secret``. Først da gis sesjon.
# Ingen sletting: avslåtte og godkjente søknader står med status og stempel.
# ---------------------------------------------------------------------------

PENDING_OPEN_MAX = 50  # abuse-tak: over dette avvises nye søknader stille
APPROVING_STALE_S = 300  # se _effective_status


def _effective_status(p: dict) -> str:
    """Status slik resten av verden skal se den.

    ``approving`` er en mellomtilstand som kun skal leve i sekundene mens
    :func:`approve_pending` oppretter brukeren. Dør prosessen HARDT (SIGKILL,
    strømbrudd) rekker verken commit eller rollback å skje, og raden ble da
    usynlig for alltid: ute av køen, og både godkjenn og avslå kastet fordi de
    krever ``open``. Morten kunne verken se eller avgjøre den (reviewer-funn
    M5/(iv)). Etter ``APPROVING_STALE_S`` regnes den derfor som ``open`` igjen
    — opprettelsen har enten lyktes (da finnes brukeren, og godkjenning feiler
    tydelig på unikhet) eller aldri skjedd.
    """
    st = p.get("status", "open")
    if st == "approving":
        since = float(p.get("approving_since") or 0)
        if not since or time.time() - since > APPROVING_STALE_S:
            return "open"
    return st


def _public_pending(p: dict) -> dict:
    """Søknad uten password_hash — hashen forlater aldri butikken."""
    return {
        "id": p.get("id", ""),
        "username": p.get("username", ""),
        "display_name": p.get("display_name", ""),
        "email": p.get("email", ""),
        "status": p.get("status", "open"),
        "created_at": p.get("created_at", ""),
        "source_ip": p.get("source_ip", ""),
        # >0 = noen har sendt inn skjemaet for DETTE brukernavnet flere ganger.
        # Kan være søkeren som prøvde igjen — eller noen som forsøkte å kapre
        # søknaden (reviewer-funn K3). Vises i admin-flaten; se før du godkjenner.
        "resubmit_count": int(p.get("resubmit_count", 0) or 0),
        "last_attempt_at": p.get("last_attempt_at", ""),
        "last_attempt_ip": p.get("last_attempt_ip", ""),
        # True = brukernavnet fantes allerede da søknaden kom; godkjenning vil
        # feile. Vist i admin-flaten, aldri utad (ville vært et enumereringsorakel).
        "collision": bool(p.get("collision")),
        "decided_at": p.get("decided_at", ""),
        "decided_by": p.get("decided_by", ""),
        "reason": p.get("reason", ""),
    }


def list_pending(include_closed: bool = False, path: Optional[Path] = None) -> list:
    """Søknader, nyeste først. Uten ``include_closed``: kun «open»."""
    items = load_store(path).get("pending") or []
    if not isinstance(items, list):
        return []
    items = [p for p in items if isinstance(p, dict)]
    # Tidligere avgjørelser for SAMME brukernavn (reviewer-funn M3): en du
    # nettopp avviste kunne søke på nytt og få en helt blank rad. Porten
    # «Morten godkjenner personen» hadde ingen hukommelse om Mortens egen
    # forrige avgjørelse. Nå følger historikken med raden.
    history = {}
    for p in items:
        st = p.get("status", "open")
        if st in ("approved", "rejected"):
            history.setdefault(p.get("username", ""), []).append(
                {"status": st, "at": p.get("decided_at", ""),
                 "by": p.get("decided_by", ""), "reason": p.get("reason", "")})
    out = []
    for p in items:
        eff = _effective_status(p)
        if not include_closed and eff != "open":
            continue
        row = _public_pending(p)
        row["status"] = eff
        row["stale_approving"] = eff != p.get("status", "open")
        row["prior_decisions"] = history.get(p.get("username", ""), [])[-3:]
        out.append(row)
    out.reverse()
    return out


def add_pending(
    *,
    username: str,
    password: str,
    display_name: str = "",
    email: str = "",
    source_ip: str = "",
    path: Optional[Path] = None,
) -> bool:
    """Registrer en søknad. Returnerer False når den avvises (ugyldig navn,
    reservert navn, kø full) — kalleren svarer likevel generisk utad, så
    skjemaet aldri blir et orakel for hvilke brukernavn som finnes.

    En ny søknad for et brukernavn som allerede har en åpen søknad ERSTATTER
    den (siste passord gjelder) i stedet for å legge en dublett i køen.
    """
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username) or username in RESERVED_USERNAMES:
        return False
    if not password or len(password) < 8 or len(password) > 256:
        return False
    # Kapping (reviewer-funn K2): feltene kommer fra en OFFENTLIG rute og
    # havner i auth-butikken, som parses ved hver eneste innlogging. Uten tak
    # kan én besøkende gjøre users.json så stor at hele innloggingsveien dør.
    display_name = (display_name or "").strip()[:80]
    email = (email or "").strip()[:200]
    with _LOCK:
        store = load_store(path)
        items = store.get("pending")
        if not isinstance(items, list):
            items = []
        open_items = [p for p in items if _effective_status(p) == "open"]
        # Kollisjon mot eksisterende bruker: søknaden tas imot (ingen lekkasje
        # utad), men flagges så Morten ser hvorfor godkjenning vil feile.
        collision = any(
            u.get("username") == username for u in store.get("users", [])
        )
        existing_idx = next(
            (i for i, p in enumerate(items)
             if _effective_status(p) == "open" and p.get("username") == username),
            -1,
        )
        if existing_idx >= 0:
            # KAPRING (reviewer-funn K3): her ERSTATTET vi tidligere raden —
            # «siste passord gjelder». Da kunne hvem som helst som gjettet et
            # brukernavn med åpen søknad sende inn sin EGEN passord-hash, og
            # Morten ville godkjent «Alice» inn i angriperens konto uten å se
            # at grunnlaget var byttet. Nå vinner den FØRSTE søknaden; senere
            # forsøk endrer ingenting, men telles og vises i admin-flaten så
            # gjentatte forsøk er synlige i stedet for stille.
            rec = items[existing_idx]
            rec["resubmit_count"] = int(rec.get("resubmit_count", 0)) + 1
            rec["last_attempt_at"] = _now()
            rec["last_attempt_ip"] = (source_ip or "")[:64]
            store["pending"] = items
            save_store(store, path)
            return True
        if len(open_items) >= PENDING_OPEN_MAX:
            return False
        # Hashing FØRST her (reviewer-funn L7): scrypt koster ~16 MiB og holder
        # den globale _LOCK-en — som blokkerer enhver innlogging imens. Ligger
        # den over gjenforsøks-returnen betaler vi den for arbeid vi kaster.
        pw_hash = hash_password(password)  # klartekst dør med denne funksjonen
        items.append({
            "id": secrets.token_hex(8),
            "username": username,
            "display_name": display_name or username,
            "email": email,
            "password_hash": pw_hash,
            "status": "open",
            "created_at": _now(),
            "source_ip": (source_ip or "")[:64],
            "collision": collision,
            "resubmit_count": 0,
            "last_attempt_at": "",
            "last_attempt_ip": "",
            "decided_at": "",
            "decided_by": "",
            "reason": "",
        })
        store["pending"] = items
        save_store(store, path)
    return True


def _find_pending(store: dict, pid: str) -> Optional[dict]:
    for p in store.get("pending") or []:
        if isinstance(p, dict) and p.get("id") == pid:
            return p
    return None


def approve_pending(
    pid: str, *, approved_by: str = "", role: str = "user",
    path: Optional[Path] = None,
) -> dict:
    """Godkjenn en søknad → oppretter brukeren med 2FA som VENTENDE krav.

    Returnerer den public bruker-dicten. 2FA-secreten returneres bevisst
    IKKE — den hører hjemme i brukerens authenticator, ikke i admin-flaten.
    """
    # Reviewer-funn (e): låsen slippes mellom lesing og create_user, og det
    # siste steget stemplet «approved» UTEN å re-sjekke status. Et avslag som
    # rakk inn i mellomtiden ble da overskrevet — kontoen ble opprettet for en
    # søknad som var avvist. Løsningen er en mellomtilstand: raden merkes
    # «approving» under låsen (og forsvinner dermed fra køen, så den ikke kan
    # godkjennes eller avslås to ganger), og rulles tilbake til «open» hvis
    # opprettelsen feiler.
    with _LOCK:
        store = load_store(path)
        rec = _find_pending(store, pid)
        if rec is None:
            raise KeyError(f"ukjent søknad: {pid}")
        if _effective_status(rec) != "open":
            raise ValueError(f"søknaden er allerede {rec.get('status')}")
        rec["status"] = "approving"
        rec["approving_since"] = time.time()
        pw_hash = str(rec.get("password_hash") or "")
        username = str(rec.get("username") or "")
        display_name = str(rec.get("display_name") or "")
        email = str(rec.get("email") or "")
        save_store(store, path)
    try:
        # create_user tar _LOCK selv — kall utenfor blokka over.
        user = create_user(
            username=username,
            password_hash=pw_hash,
            display_name=display_name,
            email=email,
            role=role,
            created_by=f"selvregistrering, godkjent av {approved_by or 'admin'}",
            totp_pending=True,
            path=path,
        )
    except BaseException:
        with _LOCK:                       # tilbake i køen, urørt
            store = load_store(path)
            rec = _find_pending(store, pid)
            if rec is not None and rec.get("status") == "approving":
                rec["status"] = "open"
                rec.pop("approving_since", None)
                save_store(store, path)
        raise
    with _LOCK:
        store = load_store(path)
        rec = _find_pending(store, pid)
        if rec is not None:
            rec["status"] = "approved"
            rec.pop("approving_since", None)
            rec["decided_at"] = _now()
            rec["decided_by"] = approved_by
            rec.pop("password_hash", None)  # hashen lever nå i bruker-raden
            save_store(store, path)
    return user


def reject_pending(
    pid: str, *, rejected_by: str = "", reason: str = "",
    path: Optional[Path] = None,
) -> dict:
    """Avslå en søknad. Raden består (vi sletter ingenting), men hashen
    fjernes — et avslag skal ikke etterlate et brukbart passord-verifikat."""
    with _LOCK:
        store = load_store(path)
        rec = _find_pending(store, pid)
        if rec is None:
            raise KeyError(f"ukjent søknad: {pid}")
        if _effective_status(rec) != "open":
            raise ValueError(f"søknaden er allerede {rec.get('status')}")
        rec["status"] = "rejected"
        rec["decided_at"] = _now()
        rec["decided_by"] = rejected_by
        rec["reason"] = (reason or "").strip()[:200]
        rec.pop("password_hash", None)
        save_store(store, path)
        return _public_pending(rec)


def pending_totp_secret(username: str, path: Optional[Path] = None) -> str:
    """Ventende (ikke-innrullert) 2FA-secret. Tom når brukeren er ferdig."""
    u = get_user(username, path) or {}
    if u.get("totp_secret"):
        return ""
    return str(u.get("totp_pending_secret") or "")


def enroll_totp(
    username: str, code: str, at_time: Optional[float] = None,
    path: Optional[Path] = None,
) -> bool:
    """Fullfør 2FA-innrullering: en gyldig kode promoterer
    ``totp_pending_secret`` → ``totp_secret``. Idempotent-trygg: virker kun
    i den ene tilstanden (ventende secret, ingen ekte ennå)."""
    username = (username or "").strip().lower()
    with _LOCK:
        store = load_store(path)
        for u in store.get("users", []):
            if u.get("username") != username:
                continue
            if u.get("disabled") or u.get("totp_secret"):
                return False
            secret = str(u.get("totp_pending_secret") or "")
            if not secret or not check_totp(secret, code, at_time=at_time):
                return False
            u["totp_secret"] = secret
            u.pop("totp_pending_secret", None)
            save_store(store, path)
            return True
    return False


def verify_login_ex(
    username: str, password: str, code: str = "",
    at_time: Optional[float] = None, path: Optional[Path] = None,
) -> dict:
    """Innloggingssjekk som også kan svare «denne må rulle inn 2FA først».

    ``{"status": "ok", "user": …}`` — full innlogging.
    ``{"status": "enroll", "user": …, "enroll": {secret, otpauth_uri}}`` —
    passord riktig, men 2FA ikke innrullert ennå: gaten skal IKKE gi sesjon.
    ``{"status": "no"}`` — generisk avvisning (aldri hvilken faktor).
    """
    # stamp=False: «sist innlogget» settes først når innloggingen faktisk
    # fullfører — ellers ville et avbrutt innrullerings-forsøk sett ut som
    # en vellykket innlogging i admin-flaten (reviewer-funn).
    user = check_login(username, password, path, stamp=False)
    if user is None:
        return {"status": "no"}
    name = user["username"]
    secret = get_totp_secret(name, path)
    if secret:
        if not check_totp(secret, code, at_time=at_time):
            return {"status": "no"}
        _stamp_login(name, path)
        return {"status": "ok", "user": user}
    pending = pending_totp_secret(name, path)
    if pending:
        return {
            "status": "enroll",
            "user": user,
            "enroll": {"secret": pending, "otpauth_uri": otpauth_uri(name, pending)},
        }
    _stamp_login(name, path)
    return {"status": "ok", "user": user}


def _stamp_login(username: str, path: Optional[Path] = None) -> None:
    with _LOCK:
        store = load_store(path)
        for u in store.get("users", []):
            if u.get("username") == username:
                u["last_login"] = _now()
                save_store(store, path)
                return


def generate_password(length: int = 16) -> str:
    """Lesbart engangspassord (4-tegns segmenter à ~23 bits, ``length`` ≈
    antall tellende tegn — reviewer-funn M2: parameteren skal virke)."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    segments = max(3, (max(8, int(length)) + 3) // 4)
    return "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(segments)
    )
