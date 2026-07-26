"""brukere plugin-API — administrasjon av chat-plattformens brukere (BL-2653).

Multiuser-planens admin-flate (charter ``plan:symbiose_multiuser_chat_platform``):
CRUD mot den delte butikken ``hermes_cli.dashboard_auth.user_store``
(users.json i HERMES_HOME). Innloggingsveien som konsumerer butikken er
``plugins/dashboard_auth/local_users``.

SIKKERHETSMODELL:
  * Rutene monteres under ``/api/plugins/brukere/`` og ligger dermed bak
    dashboardets auth-middleware (loopback-token i dag; session-cookie i
    gated modus).
  * I gated modus kreves i tillegg admin-rolle (``request.state.session``):
    en vanlig bruker skal kunne CHATTE, ikke administrere brukere.
  * Passord-hasher og signeringssecret forlater ALDRI API-et; genererte
    engangspassord returneres én gang ved opprettelse/reset.
  * Ingen DELETE — brukere deaktiveres («vi sletter ingenting»).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from hermes_cli.dashboard_auth import user_store

router = APIRouter()


def _require_admin(request: Request) -> None:
    """Admin-gate. Loopback-/token-modus (ingen session) = Morten = OK;
    gated modus krever en session hvis bruker har rolle admin i butikken."""
    session = getattr(request.state, "session", None)
    if session is None:
        return
    user = user_store.get_user(getattr(session, "user_id", "") or "")
    if not user or user.get("disabled") or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="krever admin-rolle")


def _is_admin(request: Request) -> bool:
    """True i loopback-/token-modus (lokal operatør) eller for admin-session."""
    session = getattr(request.state, "session", None)
    if session is None:
        return True
    user = user_store.get_user(getattr(session, "user_id", "") or "")
    return bool(user and not user.get("disabled") and user.get("role") == "admin")


@router.get("/status")
def status(request: Request):
    """Åpen for alle innloggede (fanen trenger den for å rendre), men
    detaljene (sti + tellinger) er admin-only — reviewer-funn M1."""
    users = user_store.list_users()
    active = [u for u in users if not u["disabled"]]
    out = {
        "bootstrap_required": not active,
        "gate_active": bool(getattr(request.app.state, "auth_required", False)),
        "is_admin": _is_admin(request),
    }
    if out["is_admin"]:
        out.update(
            store_exists=user_store.store_path().is_file(),
            store_path=str(user_store.store_path()),
            user_count=len(users),
            active_count=len(active),
            admin_count=sum(1 for u in active if u["role"] == "admin"),
        )
    return out


@router.get("/users")
def get_users(request: Request):
    _require_admin(request)
    return {"users": user_store.list_users()}


class UserIn(BaseModel):
    username: str
    display_name: str = ""
    email: str = ""
    role: str = "user"
    password: Optional[str] = None  # None => generer og returner én gang
    totp: bool = False  # True => generer 2FA-secret (returneres ÉN gang)


class UserPatch(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    disabled: Optional[bool] = None


class PasswordIn(BaseModel):
    password: Optional[str] = None  # None => generer og returner én gang


@router.post("/users")
def create_user(body: UserIn, request: Request):
    """Opprett bruker. Første bruker i tom butikk blir admin (bootstrap)."""
    _require_admin(request)
    generated = None
    password = body.password
    if not password:
        generated = user_store.generate_password()
        password = generated
    session = getattr(request.state, "session", None)
    created_by = getattr(session, "user_id", "") if session else "morten@loopback"
    try:
        user = user_store.create_user(
            username=body.username,
            password=password,
            display_name=body.display_name,
            email=body.email,
            role=body.role,
            created_by=created_by,
            totp=body.totp,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # totp_secret/otpauth_uri ligger i user-dicten KUN ved opprettelse —
    # løft dem ut som engangsfelter så user-objektet forblir hash-/secret-fritt.
    totp_secret = user.pop("totp_secret", None)
    otpauth = user.pop("otpauth_uri", None)
    out = {"user": user}
    if generated:
        out["generated_password"] = generated  # vises ÉN gang, lagres aldri
    if totp_secret:
        out["totp_secret"] = totp_secret  # vises ÉN gang (til authenticator)
        out["otpauth_uri"] = otpauth
    return out


@router.patch("/users/{username}")
def patch_user(username: str, body: UserPatch, request: Request):
    _require_admin(request)
    try:
        user = user_store.update_user(
            username,
            display_name=body.display_name,
            email=body.email,
            role=body.role,
            disabled=body.disabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"user": user}


@router.post("/users/{username}/password")
def reset_password(username: str, body: PasswordIn, request: Request):
    _require_admin(request)
    generated = None
    password = body.password
    if not password:
        generated = user_store.generate_password()
        password = generated
    try:
        user_store.set_password(username, password)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    out = {"ok": True}
    if generated:
        out["generated_password"] = generated
    return out


class TotpIn(BaseModel):
    enable: bool


@router.post("/users/{username}/totp")
def toggle_totp(username: str, body: TotpIn, request: Request):
    """Slå på (ny secret, returneres ÉN gang) eller av 2FA for en bruker."""
    _require_admin(request)
    try:
        if body.enable:
            secret = user_store.generate_totp_secret()
            user_store.set_totp(username, secret)
            return {
                "ok": True,
                "totp_secret": secret,  # vises ÉN gang (til authenticator)
                "otpauth_uri": user_store.otpauth_uri(username, secret),
            }
        user_store.set_totp(username, None)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class LoginCheckIn(BaseModel):
    username: str
    password: str
    code: str = ""
    client_ts: Optional[float] = None  # gatens NTP-riktige klokke (skew-komp.)


@router.post("/login-check")
def login_check(body: LoginCheckIn, request: Request):
    """Innloggingsverifisering for frontend-gaten (ws-proxyen på .14, over
    ssh-tunnelen — samme tillitskanal som /api/ws-broen).

    Passord + (om brukeren har 2FA) obligatorisk TOTP-kode. Generisk svar:
    aldri hvilken faktor som feilet. Ligger bak dashboardets auth-middleware
    (loopback-token / admin-session) som alle andre plugin-ruter.

    ``client_ts``: .15s klokke driver usynkronisert (chrony når ikke kildene
    gjennom brannmuren), så gaten — som HAR riktig klokke — oppgir sitt
    tidspunkt for TOTP-vinduet. Aksepteres kun innen ±15 min av server-tid
    (calleren er allerede token-autentisert; bindingen begrenser skaden om
    noe skulle gå galt oppstrøms).
    """
    _require_admin(request)
    import time as _time

    # ±300 s: rommer dagens ~2 min skew med margin, men krymper vinduet en
    # kompromittert oppstrøms-caller kunne utnytte (reviewer-funn b1).
    at_time = None
    if body.client_ts is not None and abs(body.client_ts - _time.time()) < 300:
        at_time = float(body.client_ts)
    user = user_store.verify_login(
        body.username, body.password, body.code, at_time=at_time
    )
    if user is None:
        return {"ok": False}
    return {"ok": True, "user": user}


@router.get("/user-active/{username}")
def user_active(username: str, request: Request):
    """Lettvekts aktiv-sjekk for frontend-gatens cookie-verifisering:
    deaktivering på .15 skal drepe frontend-tilgang innen cache-vinduet."""
    _require_admin(request)
    user = user_store.get_user(username)
    if not user or user.get("disabled"):
        return {"active": False}
    return {"active": True, "role": user.get("role", "user"),
            "display_name": user.get("display_name") or username}


class BootstrapMigrateIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    email: str = ""
    totp_secret: str = ""


@router.post("/bootstrap-migrate")
def bootstrap_migrate(body: BootstrapMigrateIn, request: Request):
    """Engangs-migrering av frontend-gatens eksisterende enbruker-innlogging
    (.auth.json på .14: passphrase + TOTP-secret) inn som FØRSTE bruker
    (admin). VIRKER KUN NÅR BUTIKKEN ER TOM — etterpå er ruta død. Kalles
    maskin-til-maskin over tunnelen; hemmelighetene passerer aldri en chat.
    """
    _require_admin(request)
    if any(not u["disabled"] for u in user_store.list_users()):
        raise HTTPException(status_code=409, detail="butikken er ikke tom")
    try:
        user = user_store.create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
            role="admin",
            created_by="bootstrap-migrate(.auth.json)",
            totp_secret=body.totp_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    user.pop("totp_secret", None)
    user.pop("otpauth_uri", None)
    return {"ok": True, "user": user}
