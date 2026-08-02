"""LocalUsersProvider — flerbruker passord-auth mot users.json (BL-2653).

Multiuser-planens innloggingsvei (charter ``plan:symbiose_multiuser_chat_platform``,
Phase 1/3): samme ``DashboardAuthProvider``-ramme som ``basic``, men mot den
delte bruker-butikken ``hermes_cli.dashboard_auth.user_store`` (users.json i
HERMES_HOME) i stedet for én konfig-bruker. Admin-flaten som redigerer butikken
er ``plugins/brukere`` («Brukere»-fanen i GUI-et).

Egenskaper:
  * ``supports_password = True`` — login-siden rendrer skjema automatisk når
    dashboardet bindes gated; loopback-/token-modus er upåvirket (gate av).
  * Sesjoner = statsløse HMAC-tokens (samme mønster som ``basic``), signert
    med butikkens secret → overlever restart uten egen konfig.
  * ``verify_session`` slår opp brukeren PER request: deaktivering i
    «Brukere»-fanen dreper levende sesjoner umiddelbart (fail-lukket).
  * Rollen (admin/user) bæres i ``Session.org_id`` — provider-spesifikt
    felt, brukt av brukere-API-et for admin-gating i gated modus.
  * Registrerer seg kun når butikken har ≥1 aktiv bruker; ellers settes
    ``LAST_SKIP_REASON`` (samme kontrakt som de andre providerne).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from hermes_cli.dashboard_auth import (
    DashboardAuthProvider,
    InvalidCredentialsError,
    LoginStart,
    RefreshExpiredError,
    Session,
)
from hermes_cli.dashboard_auth import user_store

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 12 * 60 * 60  # 12t access-token (refresh forlenger)
_REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60  # 30d
_SIG_LEN = hashlib.sha256().digest_size

LAST_SKIP_REASON: str = ""


def _sign(payload: dict, secret: bytes) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret, raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + sig).decode()


def _unsign(token: str, secret: bytes) -> Optional[dict]:
    try:
        blob = base64.urlsafe_b64decode(token.encode())
        if len(blob) <= _SIG_LEN:
            return None
        raw, sig = blob[:-_SIG_LEN], blob[-_SIG_LEN:]
        expected = hmac.new(secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(raw)
    except Exception:
        return None


class LocalUsersProvider(DashboardAuthProvider):
    """Passord-provider mot den delte users.json-butikken."""

    name = "local_users"
    display_name = "Symbiose-bruker"
    supports_password = True

    # ---- OAuth-metoder: ikke i bruk (ren passord-provider) -----------------

    def start_login(self, *, redirect_uri: str) -> LoginStart:
        raise NotImplementedError(
            "LocalUsersProvider er passord-basert; login-siden POSTer til "
            "/auth/password-login."
        )

    def complete_login(
        self, *, code: str, state: str, code_verifier: str, redirect_uri: str
    ) -> Session:
        raise NotImplementedError(
            "LocalUsersProvider er passord-basert; bruk complete_password_login."
        )

    # ---- passord-innlogging ------------------------------------------------

    def complete_password_login(self, *, username: str, password: str) -> Session:
        # stamp=False (reviewer-funn M1): uten den stemplet en NEKTET
        # innlogging «sist innlogget» — samme løgn som stamp-flagget ble
        # innført for å fjerne. Stemples nedenfor, når sesjonen faktisk mynter.
        user = user_store.check_login(username, password, stamp=False)
        if user is None:
            raise InvalidCredentialsError("invalid username or password")
        # BL-3404: denne veien er REN passord-innlogging — den har ikke noe
        # kodefelt, og kan derfor ikke verifisere en andre faktor. Slipper den
        # gjennom en bruker som HAR 2FA, er den en bakdør rundt kravet den
        # dagen dashboardet bindes gated. Derfor nektes begge tilstandene:
        #   · totp_secret satt      → 2FA er påkrevd, og kan ikke sjekkes her
        #   · totp_pending_secret   → godkjent søker, ikke innrullert ennå
        # (Første utkast lukket kun den andre — reviewer-funn.) Morten selv har
        # 2FA, så denne stien er i praksis stengt for alle med andre faktor;
        # skal dashboardet få passord-innlogging må den lære TOTP først.
        name = user["username"]
        if user_store.has_totp(name) or user_store.pending_totp_secret(name):
            raise InvalidCredentialsError(
                "kontoen krever 2FA; denne innloggingsveien støtter ikke koden"
            )
        session = self._mint_session(user)
        user_store._stamp_login(name)
        return session

    # ---- sesjonslivssyklus -------------------------------------------------

    def _secret(self) -> bytes:
        return user_store.signing_secret(user_store.load_store())

    def verify_session(self, *, access_token: str) -> Optional[Session]:
        secret = self._secret()
        if not secret:
            return None
        payload = _unsign(access_token, secret)
        if (
            payload is None
            or payload.get("kind") != "access"
            or payload.get("exp", 0) <= int(time.time())
        ):
            return None
        # Oppslag per verify: deaktivert/fjernet bruker = død sesjon nå.
        user = user_store.get_user(str(payload.get("sub", "")))
        if user is None or user.get("disabled"):
            return None
        return Session(
            user_id=user["username"],
            email=user.get("email", ""),
            display_name=user.get("display_name") or user["username"],
            org_id=user.get("role", "user"),
            provider=self.name,
            expires_at=int(payload["exp"]),
            access_token=access_token,
            refresh_token="",
        )

    def refresh_session(self, *, refresh_token: str) -> Session:
        if not refresh_token:
            raise RefreshExpiredError("no refresh token present in session")
        secret = self._secret()
        payload = _unsign(refresh_token, secret) if secret else None
        if (
            payload is None
            or payload.get("kind") != "refresh"
            or payload.get("exp", 0) <= int(time.time())
        ):
            raise RefreshExpiredError("refresh token expired or invalid")
        user = user_store.get_user(str(payload.get("sub", "")))
        if user is None or user.get("disabled"):
            raise RefreshExpiredError("user disabled or unknown")
        return self._mint_session(user)

    def revoke_session(self, *, refresh_token: str) -> None:
        # Statsløse tokens — ingenting å tilbakekalle server-side; TTL rår.
        _ = refresh_token
        return None

    # ---- intern ------------------------------------------------------------

    def _mint_session(self, user: dict) -> Session:
        secret = self._secret()
        if not secret:
            raise InvalidCredentialsError("user store has no signing secret")
        now = int(time.time())
        exp = now + _DEFAULT_TTL_SECONDS
        access_token = _sign(
            {"sub": user["username"], "kind": "access", "exp": exp}, secret
        )
        refresh_token = _sign(
            {
                "sub": user["username"],
                "kind": "refresh",
                "exp": now + _REFRESH_TTL_SECONDS,
            },
            secret,
        )
        return Session(
            user_id=user["username"],
            email=user.get("email", ""),
            display_name=user.get("display_name") or user["username"],
            org_id=user.get("role", "user"),
            provider=self.name,
            expires_at=exp,
            access_token=access_token,
            refresh_token=refresh_token,
        )


def register(ctx) -> None:
    """Plugin-entry — registrerer provideren når butikken har aktive brukere."""
    global LAST_SKIP_REASON
    LAST_SKIP_REASON = ""

    try:
        users = [u for u in user_store.list_users() if not u.get("disabled")]
    except Exception as exc:  # noqa: BLE001 — butikk-feil skal aldri velte lasting
        LAST_SKIP_REASON = f"users.json uleselig: {exc}"
        logger.warning("dashboard-auth-local_users: %s", LAST_SKIP_REASON)
        return

    if not users:
        LAST_SKIP_REASON = (
            "ingen aktive brukere i users.json enda — opprett den første "
            "(admin) i «Brukere»-fanen i dashboardet."
        )
        logger.info("dashboard-auth-local_users: %s", LAST_SKIP_REASON)
        return

    ctx.register_dashboard_auth_provider(LocalUsersProvider())
    logger.info(
        "dashboard-auth-local_users: registrert (%d aktive brukere)", len(users)
    )
