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
# BL-3432/ADR-046 rev2 (Morten: «kari og ola skal være user og superuser»):
# TRE roller, fordi EVNE og MYNDIGHET er to forskjellige ting.
#   admin      ser alt  +  administrerer brukere        (= owner)
#   superuser  ser alt  +  administrerer INGEN
#   user       ser det som er krysset av for dem
# Superuser fyller hullet ADR-046 §D4 navnga: modellen kunne ikke uttrykke
# «full tilgang uten styringsrett». Nå kan den.
ROLES = ("admin", "superuser", "user")
# Rollene som ser HELE katalogen. Bevisst egen konstant og ikke en test på
# `!= "user"` — legges en fjerde rolle til, skal den ikke arve alt ved et uhell.
FULL_ACCESS_ROLES = ("admin", "superuser")
# Rollen som får styre andre. Egen konstant av samme grunn.
ADMIN_ROLES = ("admin",)

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
        # BL-3428/ADR-046: hvilke skill-kategorier denne brukeren har fått UTOVER
        # de system-klassifiserte. Tom liste = kun system (ADR-045 D2, fail-closed).
        "granted_capabilities": list(u.get("granted_capabilities") or []),
        "username": u.get("username", ""),
        "display_name": u.get("display_name", ""),
        "email": u.get("email", ""),
        "role": u.get("role", "user"),
        "disabled": bool(u.get("disabled", False)),
        "created_at": u.get("created_at", ""),
        "created_by": u.get("created_by", ""),
        "last_login": u.get("last_login", ""),
        "has_totp": bool(u.get("totp_secret")),
        # Ser hele katalogen? Avledet av rollen, så flaten slipper å gjette.
        "full_access": u.get("role") in FULL_ACCESS_ROLES,
    }


def list_users(path: Optional[Path] = None) -> list[dict]:
    return [_public(u) for u in load_store(path).get("users", [])]


def get_user(username: str, path: Optional[Path] = None) -> Optional[dict]:
    for u in load_store(path).get("users", []):
        if u.get("username") == username:
            return dict(u)
    return None


# ── BL-3428 / ADR-046: kapabilitets-styring ────────────────────────────────
# «HVA er artefaktet» bor i skillen (frontmatter, ADR-045 D1). «HVEM får det»
# bor her, hos brukeren — en tildeling handler om en person, ikke om et verktøy.
# Kategori-klassifiseringen er det mellomliggende laget for de 113 skillene som
# ikke erklærer noe selv; den bor i butikkens `capability_policy`.


def get_capability_policy(path: Optional[Path] = None) -> dict:
    """Mortens klassifisering av skill-kategoriene. Tom = ingenting klassifisert,
    og da gjelder fail-closed-defaulten for alt (ADR-045 D2)."""
    pol = load_store(path).get("capability_policy")
    return pol if isinstance(pol, dict) else {"categories": {}}


def set_capability_policy(categories: dict, path: Optional[Path] = None) -> dict:
    """Klassifiser kategorier. Kun 'system' | 'owner' | 'steward:<navn>' godtas —
    en ugyldig verdi lagres ALDRI, for da ville den blitt lest som «ukjent» og
    falt til default, og Morten ville trodd han hadde satt noe han ikke hadde."""
    import re as _re
    ok = _re.compile(r"^(system|owner|steward:[a-z0-9_.-]{1,40})$")
    clean = {}
    for k, v in (categories or {}).items():
        k = str(k).strip()[:64]
        v = str(v).strip()
        if not k:
            continue
        if v == "":
            continue                    # tom = fjern klassifiseringen
        if not ok.match(v):
            raise ValueError(f"ugyldig synlighet {v!r} for kategori {k!r}")
        clean[k] = v
    with _LOCK:
        store = load_store(path)
        store["capability_policy"] = {"categories": clean, "updated_at": _now()}
        save_store(store, path)
        return store["capability_policy"]


def set_granted_capabilities(username: str, granted: list,
                             path: Optional[Path] = None) -> dict:
    """Sett hvilke kategorier/skills en bruker får utover de system-klassifiserte."""
    clean = sorted({str(g).strip()[:64] for g in (granted or []) if str(g).strip()})
    if len(clean) > 200:
        raise ValueError("for mange tildelinger (maks 200)")
    with _LOCK:
        store = load_store(path)
        for u in store.get("users", []):
            if u.get("username") == username:
                u["granted_capabilities"] = clean
                save_store(store, path)
                return _public(u)
    raise KeyError(f"ukjent bruker: {username}")


def policy_health(path: Optional[Path] = None) -> dict:
    """Er policy-infrastrukturen frisk? Brukes av /brukere til å SI FRA.

    B1 (reviewer, KRITISK): gaten og styringsflaten kjørte i ULIKE HERMES_HOME
    (dashboard ~/.hermes-gui med users.json + 115 skills; gatewayen ~/.hermes
    med 93 skills og INGEN users.json). Butikken er derfor pinnet kanonisk. Men
    en pinning som er FEIL må ikke feile stille — den må være synlig i flaten.
    """
    try:
        from hermes_cli.dashboard_auth import capability_policy as cp
        canon = cp.canonical_users_path()
    except Exception as exc:
        return {"ok": False, "reason": f"policy-modulen mangler: {exc}"}
    local = store_path()
    return {
        "ok": canon.is_file(),
        "canonical_store": str(canon),
        "canonical_exists": canon.is_file(),
        "local_store": str(local),
        # True = flaten du styrer i, og butikken gaten leser, er SAMME fil.
        "same_store": str(canon) == str(local),
        "reason": "" if canon.is_file() else
                  f"kanonisk butikk finnes ikke: {canon} — sett {cp.CANONICAL_HOME_ENV}",
    }


def resolve_disabled_skills(username: str, path: Optional[Path] = None) -> set:
    """Skill-navn som SKAL skjules for denne prinsipalen.

    Dette er funksjonen runtime-gaten (agent.skill_utils.get_disabled_skill_names)
    kaller.

    TO STIER, TO OPPHAV (B1):
      · BUTIKKEN leses KANONISK (capability_policy.canonical_users_path) —
        ikke fra kallerens HERMES_HOME. En autorisasjonsavgjørelse kan ikke
        henge på en kontekst-overstyrbar sti.
      · SKILLS-TREET skannes LOKALT hos kalleren, fordi vi returnerer navn på
        de skillene runtimen faktisk har. De to hjemmene har drevet 22 fra
        hverandre, og det er en pre-eksisterende defekt (ADR-045 §1) — men det
        er runtimens eget tre som er sannheten om hva den kan vise.

    FEILRETNING — og hvorfor den IKKE er fail-closed her:
    Finner vi ikke den kanoniske butikken, kan vi ikke skille noen fra noen.
    Å fail-CLOSE da ville skjult ALT for ALLE — nøyaktig skaden B1 ville
    forårsaket, og et driftsavbrudd for eieren utløst av en sti-feil. Vi faller
    derfor til status quo (ingen filtrering) og SIER FRA via policy_health(),
    som /brukere viser. Trusselen dette åpner for — noen som kan slette
    users.json på .15 — eier allerede boksen.
    En KJENT bruker som ikke har fått noe får derimot fortsatt kun det
    system-klassifiserte: DER er fail-closed riktig, fordi vi VET hvem de er.
    """
    try:
        from hermes_cli.dashboard_auth import capability_policy as cp
    except Exception:
        return set()          # policy-laget finnes ikke → gaten som før
    canon = cp.canonical_users_path()
    if not canon.is_file():
        return set()          # se docstring: status quo + signal, ikke blackout
    p = path or canon
    username = (username or "").strip().lower()
    u = get_user(username, p) if username else None
    pol = get_capability_policy(p)
    if u is None or u.get("disabled"):
        return cp.disabled_for("", is_owner=False, granted=[], policy=pol)
    return cp.disabled_for(
        username,
        is_owner=(u.get("role") in FULL_ACCESS_ROLES),
        granted=u.get("granted_capabilities") or [],
        policy=pol,
    )


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
    path: Optional[Path] = None,
) -> dict:
    """Opprett bruker. Første bruker i en tom butikk MÅ være admin
    (bootstrap — «jeg som første og eneste bruker»), og genererer
    samtidig signeringssecreten. ``totp=True`` genererer 2FA-secret
    (``totp_secret`` kan overstyre — migreringsveien fra .auth.json);
    secreten returneres da ÉN gang i feltet ``totp_secret``.

    BL-3404 (selvregistrering): ``password_hash`` OG ``totp_secret`` lar
    godkjenningsveien gjenbruke det søkeren laget da de fylte skjemaet —
    klartekst-passordet forlot aldri den ene requesten, og 2FA-nøkkelen ble
    verifisert med en ekte kode før søknaden i det hele tatt ble sendt.
    Godkjenningen returnerer secreten ALDRI: den bor i søkerens egen
    authenticator, ikke i admin-flaten (én hemmelighet, én mottaker)."""
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
        generate_totp_secret() if totp else ""
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
            user["totp_secret"] = secret_b32
        store["users"].append(user)
        save_store(store, path)
    out = _public(user)
    if secret_b32 and not totp_secret:
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
                u.pop("totp_pending_secret", None)   # rydder evt. arv fra rev1
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
    secret = get_totp_secret(user["username"], path)
    if secret and not check_totp(secret, code, at_time=at_time):
        return None
    _stamp_login(user["username"], path)   # kun ved FULLFØRT innlogging
    return user


def has_totp(username: str, path: Optional[Path] = None) -> bool:
    return bool(get_totp_secret(username, path))


# ---------------------------------------------------------------------------
# BL-3404 rev2: selvregistrering med admin-godkjenning og 2FA I SKJEMAET
#
# Flyten, og hvorfor den ser slik ut:
#   1. Besøkende fyller skjemaet på ai.byopus.com — INKLUDERT tofaktor: gaten
#      viser en TOTP-nøkkel og krever en gyldig kode før noe sendes videre.
#   2. Gaten sender det server-til-server hit over SAMME ssh-tunnel som
#      login-check, med den verifiserte nøkkelen.
#   3. Passordet hashes HER, i requesten som bar det. Ingen klartekst når
#      noen gang disk, logg eller admin-flate.
#   4. Søknaden ligger som «open» til Morten godkjenner i /brukere. En søknad
#      UTEN gyldig nøkkel avvises — alt som når admin-flaten er 2FA-sikret.
#   5. Godkjenning oppretter brukeren med den lagrede hashen OG nøkkelen.
#      Nøkkelen returneres ALDRI til admin: den bor i søkerens authenticator.
#      Fra første innlogging kreves passord + kode, som for alle andre.
#
#   rev1 utsatte 2FA til søkerens første innlogging («innrullering»). Morten
#   spurte tre ganger hvor 2FA var på registreringssiden — den var usynlig
#   nettopp der man forventer den, og den etterlot en godkjent konto som
#   ENFAKTOR til søkeren kom tilbake. Steget er fjernet i sin helhet, og med
#   det den andre signerte token-typen som ga K1.
#
# Ingen sletting: avslåtte, godkjente og utløpte søknader står med status og
# stempel — men uten hemmeligheter (_strip_secrets).
PENDING_OPEN_MAX = 50  # abuse-tak: over dette avvises nye søknader stille
ATTEMPTS_MAX = 5       # innsendinger per åpen søknad som beholdes i sin helhet
# F7/(g): en ÅPEN søknad bærer nå et komplett legitimasjonspar — passord-hash
# OG et levende TOTP-frø — for en konto som ikke finnes ennå. Uten utløp ligger
# det i ro på disk (og i backup) til noen bestemmer seg. Etter denne fristen
# auto-avslås søknaden og hemmelighetene strippes. Det lukker samtidig
# kø-fyllingen og «avvist søker søker på nytt»-slitasjen.
PENDING_TTL_S = 14 * 24 * 3600
APPROVING_STALE_S = 300  # se _effective_status


def _pending_age(p: dict) -> float:
    """Alder i sekunder. ``created_epoch`` er autoritativ; eldre rader uten
    den faller tilbake til å parse ``created_at`` (og regnes som ferske hvis
    heller ikke det lar seg lese — en uleselig dato skal ikke auto-avslå noen)."""
    try:
        return max(0.0, time.time() - float(p.get("created_epoch") or 0)) \
            if p.get("created_epoch") else \
            max(0.0, time.time() - time.mktime(time.strptime(
                str(p.get("created_at", ""))[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError, OverflowError):
        return 0.0


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
            st = "open"        # krasjet midt i godkjenning — tilbake i køen
    # G2 (reviewer): TTL-sjekken MÅ komme etter demoteringen over. Sto den
    # først, ble en krasjet «approving»-rad aldri «expired», og beholdt hash
    # + TOTP-frø i ubegrenset tid — F6 dekket kun tilfellet der brukeren
    # FAKTISK ble opprettet.
    if st == "open" and _pending_age(p) > PENDING_TTL_S:
        return "expired"
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
        # Hver innsending, uten hash og uten 2FA-nøkkel. Er det mer enn én må
        # Morten velge hvilken som skal bli kontoen — nr. 0 er standard.
        "attempts": [{"at": a.get("at", ""), "ip": a.get("ip", ""),
                      "display_name": a.get("display_name", ""),
                      "email": a.get("email", "")}
                     for a in (p.get("attempts") or []) if isinstance(a, dict)],
        # True = brukernavnet fantes allerede da søknaden kom; godkjenning vil
        # feile. Vist i admin-flaten, aldri utad (ville vært et enumereringsorakel).
        "collision": bool(p.get("collision")),
        "decided_at": p.get("decided_at", ""),
        "decided_by": p.get("decided_by", ""),
        "reason": p.get("reason", ""),
    }


def expire_stale_pending(path: Optional[Path] = None) -> int:
    """Auto-avslå åpne søknader eldre enn ``PENDING_TTL_S`` og STRIPP dem.

    Kalles fra :func:`list_pending`, altså hver gang admin-flaten polles —
    det er den eneste jevnlige pulsen butikken har. En ren lesefunksjon som
    skriver er ikke pent, men alternativet er at hemmelighetene ligger igjen
    til noen tilfeldigvis kjører noe annet."""
    n = 0
    with _LOCK:
        store = load_store(path)
        for p in store.get("pending") or []:
            # _effective_status, ikke råfeltet (G2): ellers hopper denne over
            # nøyaktig de radene som trenger den mest — de som krasjet i
            # «approving» og bærer et levende TOTP-frø.
            if not isinstance(p, dict) or _effective_status(p) != "expired":
                continue
            p["status"] = "expired"
            p["decided_at"] = _now()
            p["decided_by"] = "auto (utløpt, %d dager)" % (PENDING_TTL_S // 86400)
            _strip_secrets(p)
            n += 1
        if n:
            save_store(store, path)
    return n


def list_pending(include_closed: bool = False, path: Optional[Path] = None) -> list:
    """Søknader, nyeste først. Uten ``include_closed``: kun «open»."""
    expire_stale_pending(path)
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
        if st in ("approved", "rejected", "expired"):
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
    totp_secret: str = "",
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
    # BL-3404 rev2 (Morten: «hvor er 2fa???»): 2FA settes opp i REGISTRERINGS-
    # skjemaet, ikke ved første innlogging. Gaten har allerede verifisert en
    # gyldig kode mot denne nøkkelen før søknaden sendes hit — en søknad UTEN
    # nøkkel er derfor ikke en gyldig søknad, og avvises. Det er den mekaniske
    # garantien for at alt som når admin-flaten er ferdig 2FA-sikret.
    totp_secret = (totp_secret or "").strip().upper()
    if not re.match(r"^[A-Z2-7]{16,64}$", totp_secret):
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
            # KAPRING (reviewer-funn K3) vs. MISTET TELEFON — begge løses her.
            #
            # Opprinnelig ERSTATTET vi raden («siste passord gjelder»), og da
            # kunne hvem som helst som gjettet et brukernavn med åpen søknad
            # sende inn sin EGEN hash, og Morten ville godkjent «Alice» inn i
            # angriperens konto uten å se at grunnlaget var byttet.
            # Neste utkast lot den FØRSTE vinne og forkastet resten — trygt,
            # men da satt en søker som mistet telefonen mellom registrering og
            # godkjenning fast: de kunne ikke sende inn på nytt.
            #
            # Nå BEVARES hver innsending som et eget forsøk. Den FØRSTE er
            # fortsatt standard, så ingen kan bytte grunnlaget stille — men
            # Morten kan bevisst velge et senere forsøk når søkeren sier de
            # måtte gjøre det om igjen. Valget er hans, og det er synlig.
            rec = items[existing_idx]
            atts = rec.setdefault("attempts", [])
            rec["resubmit_count"] = int(rec.get("resubmit_count", 0)) + 1
            rec["last_attempt_at"] = _now()
            rec["last_attempt_ip"] = (source_ip or "")[:64]
            if len(atts) < ATTEMPTS_MAX:
                atts.append({
                    "at": _now(), "ip": (source_ip or "")[:64],
                    "display_name": display_name or username, "email": email,
                    "password_hash": hash_password(password),
                    "totp_secret": totp_secret,
                })
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
            "attempts": [{
                "at": _now(), "ip": (source_ip or "")[:64],
                "display_name": display_name or username, "email": email,
                "password_hash": pw_hash,
                "totp_secret": totp_secret,
            }],
            "status": "open",
            "created_at": _now(),
            "created_epoch": time.time(),
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


def _reopen_approving(pid: str, path: Optional[Path]) -> None:
    """Legg en «approving»-rad tilbake i køen, urørt, så et nytt forsøk virker."""
    with _LOCK:
        store = load_store(path)
        rec = _find_pending(store, pid)
        if rec is not None and rec.get("status") == "approving":
            rec["status"] = "open"
            rec.pop("approving_since", None)
            save_store(store, path)


def _strip_secrets(rec: dict) -> None:
    """Fjern hash og 2FA-nøkkel fra en AVGJORT søknad — fra raden selv OG fra
    hvert forsøk. En avgjort søknad skal aldri være en andre kopi av noe som
    kan brukes til å logge inn."""
    rec.pop("password_hash", None)
    rec.pop("totp_secret", None)
    for a in (rec.get("attempts") or []):
        if isinstance(a, dict):
            a.pop("password_hash", None)
            a.pop("totp_secret", None)


def _find_pending(store: dict, pid: str) -> Optional[dict]:
    for p in store.get("pending") or []:
        if isinstance(p, dict) and p.get("id") == pid:
            return p
    return None


def approve_pending(
    pid: str, *, approved_by: str = "", role: str = "user",
    attempt: int = 0, path: Optional[Path] = None,
) -> dict:
    """Godkjenn en søknad → oppretter brukeren, ferdig 2FA-sikret.

    ``attempt`` velger hvilken innsending som blir kontoen. 0 (standard) er
    den FØRSTE — så ingen kan bytte grunnlaget stille ved å sende inn på nytt.
    Et senere forsøk krever at Morten aktivt peker på det, hvilket er nøyaktig
    når han har snakket med søkeren (typisk: «jeg mistet telefonen».

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
        atts = rec.get("attempts") or []
        if not isinstance(atts, list) or not atts:
            raise ValueError("søknaden har ingen innsendinger")
        if not (0 <= attempt < len(atts)):
            raise ValueError(
                f"ukjent innsending {attempt} (søknaden har {len(atts)})")
        a = atts[attempt]
        username = str(rec.get("username") or "")
        pw_hash = str(a.get("password_hash") or "")
        display_name = str(a.get("display_name") or "")
        email = str(a.get("email") or "")
        totp_secret = str(a.get("totp_secret") or "")
        save_store(store, path)
    try:
        # create_user tar _LOCK selv — kall utenfor blokka over.
        user = create_user(
            username=username,
            password_hash=pw_hash,
            display_name=display_name,
            email=email,
            role=role,
            created_by=("selvregistrering, godkjent av %s%s"
                        % (approved_by or "admin",
                           "" if attempt == 0 else " (innsending nr. %d)" % (attempt + 1))),
            totp_secret=totp_secret,
            path=path,
        )
    except ValueError as exc:
        # F6 (reviewer): dør prosessen ETTER at create_user lyktes men FØR
        # stemplingen, står raden igjen som «approving» → «open» med en levende
        # passord-hash OG et levende TOTP-frø til en konto som NÅ finnes. Neste
        # godkjenning feiler på unikhet, og uten dette rullet vi bare tilbake
        # igjen — hemmelighetene ble liggende til noen avslo manuelt.
        # «Finnes allerede» på en approving-rad betyr at opprettelsen FAKTISK
        # skjedde: stemple ferdig og strippe er riktig utfall, ikke rollback.
        # MEN: «finnes allerede» betyr ikke alltid at VI laget den. En ekte
        # navnekollisjon (søknad om et navn som alt er i bruk) gir samme feil,
        # og den skal IKKE stemples som godkjent — den skal tilbake i køen så
        # Morten kan avvise den. Skillet er eksakt: hvis den eksisterende
        # brukeren bærer NØYAKTIG hashen fra denne innsendingen, er det vår
        # egen fullførte opprettelse vi ser. Ellers er det en fremmed konto.
        ours = False
        if "finnes allerede" in str(exc) and pw_hash:
            existing = get_user(username, path) or {}
            ours = hmac.compare_digest(
                str(existing.get("password_hash", "")).encode(), pw_hash.encode())
        if ours:
            with _LOCK:
                store = load_store(path)
                rec = _find_pending(store, pid)
                if rec is not None and rec.get("status") == "approving":
                    rec["status"] = "approved"
                    rec.pop("approving_since", None)
                    rec["decided_at"] = _now()
                    rec["decided_by"] = approved_by
                    rec["decided_attempt"] = attempt
                    rec["note"] = "konto fantes alt — antatt fullført godkjenning"
                    _strip_secrets(rec)
                    save_store(store, path)
            # Dette ER et vellykket utfall (kontoen finnes, laget av nettopp
            # denne innsendingen) — returner brukeren i stedet for å kaste
            # 422 «finnes allerede» i ansiktet på Morten (reviewer (i)).
            existing = get_public_user(username, path)
            if existing is not None:
                return existing
        else:
            _reopen_approving(pid, path)
        raise
    except BaseException:
        _reopen_approving(pid, path)
        raise
    with _LOCK:
        store = load_store(path)
        rec = _find_pending(store, pid)
        if rec is not None:
            rec["status"] = "approved"
            rec.pop("approving_since", None)
            rec["decided_at"] = _now()
            rec["decided_by"] = approved_by
            # Hash OG 2FA-nøkkel lever nå i bruker-raden — søknaden skal ikke
            # bli en andre kopi av noen av dem.
            rec["decided_attempt"] = attempt
            _strip_secrets(rec)
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
        _strip_secrets(rec)   # et avslag etterlater verken hash eller nøkkel
        save_store(store, path)
        return _public_pending(rec)


def verify_login_ex(
    username: str, password: str, code: str = "",
    at_time: Optional[float] = None, path: Optional[Path] = None,
) -> dict:
    """Innloggingssjekk som også kan svare «denne må rulle inn 2FA først».

    ``{"status": "ok", "user": …}`` — full innlogging.
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
