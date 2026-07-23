"""tilgang plugin-API — tilgangskartet + creds-lager (BL-2378).

SIKKERHETSMODELL (arver jetstreams D5, reviewer-godkjent):
  - Kartet (:AccessRoute) leses read-only fra grafen. Det bærer KUN metadata
    (fra/til/metode/formål/status/store-slot-NAVN) — ALDRI hemmeligheter.
  - Creds (sudo-passord, tokens) settes write-only via forced-command-kanalen
    .15→.11 (samme kanal som nøkkelpanelet): 'set NAVN' tar verdi på stdin,
    'list' gir navn+fingeravtrykk. get/rm NEKTES av gaten. Verdier bor kun
    som 0600-filer i .11-storen; vises aldri i graf/API/GUI.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
API_BASE = (os.environ.get("SYMBIOSE_API_URL") or "http://192.168.40.12:8010").rstrip("/")
_SSH_KEYCHANNEL = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                   "-i", os.path.expanduser("~/.ssh/id_ed25519_jetstream"),
                   "mnemosyne@192.168.40.11"]
KEYNAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

_Q_ROUTES = (
    "MATCH (a:AccessRoute) "
    "RETURN a.from_host AS from_host, a.to_host AS to_host, a.method AS method, "
    "a.credential AS credential, a.purpose AS purpose, a.status AS status, "
    "a.store_slot AS store_slot ORDER BY a.status, a.from_host, a.to_host"
)


def _graph(query: str, limit: int = 100):
    url = f"{API_BASE}/graph/query?query={urllib.parse.quote(query)}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r).get("results", [])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"graf utilgjengelig: {e}")


@router.get("/routes")
def routes():
    return {"routes": _graph(_Q_ROUTES, 100)}


@router.get("/store")
def store():
    """Navn + fingeravtrykk fra .11-storen (aldri verdier)."""
    try:
        r = subprocess.run(_SSH_KEYCHANNEL + ["list"], capture_output=True,
                           text=True, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"store utilgjengelig: {e}")
    keys = []
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            keys.append({"name": parts[0], "fingerprint": parts[1],
                         "mtime": parts[2] if len(parts) > 2 else ""})
    return {"keys": keys}


class CredIn(BaseModel):
    name: str
    value: str


@router.put("/cred")
def set_cred(c: CredIn):
    """Write-only: verdi går til .11-storen via forced-command; aldri logget/vist."""
    if not KEYNAME_RE.match(c.name or ""):
        raise HTTPException(422, f"ugyldig navn: {c.name!r} (krav {KEYNAME_RE.pattern})")
    if not c.value:
        raise HTTPException(422, "tom verdi")
    try:
        r = subprocess.run(_SSH_KEYCHANNEL + [f"set {c.name}"], input=c.value,
                           capture_output=True, text=True, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"kanal utilgjengelig: {e}")
    if r.returncode != 0:
        raise HTTPException(status_code=502, detail=(r.stderr or "set feilet")[:200])
    # returner KUN fingeravtrykk-bekreftelsen fra gatens stderr, aldri verdien
    return {"ok": True, "detail": (r.stderr or "").strip()[:120]}
