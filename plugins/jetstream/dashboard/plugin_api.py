"""Jetstream dashboard plugin — backend API (BL-2348).

Mounted at /api/plugins/jetstream/ by the dashboard plugin system, behind the
session-token auth middleware (same contract as kanban — see its docstring).

Tynt lag over unified-API-ets READ-ONLY /graph/query på flåten (.12:8010) —
samme sikkerhetsmodell som tools/symbiose_tools.py (BL-2289-allowlisten):
ingen graf-credentials på .15, ingen klient-levert Cypher (alle spørringer er
FASTE strenger her; klienten kan bare velge hvilken). Registeret
(:IngestSourceSpec, seedet av AGI-repoets tools/jetstream_registry.py) er
sannhetskilden; denne fila legger ikke egen tilstand.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter()

API_BASE = os.environ.get("SYMBIOSE_API_URL", "http://192.168.40.12:8010").rstrip("/")

# FASTE spørringer — klient-input når aldri Cypher-strengen.
_Q_SOURCES = (
    "MATCH (j:IngestSourceSpec) "
    "OPTIONAL MATCH (j)-[:CONSUMED_BY]->(c) "
    "RETURN j.name AS name, j.source_kind AS kind, j.domain AS domain, "
    "       j.migration_status AS migration, j.consumer_status AS consumer_status, "
    "       j.endpoint_hint AS endpoint, j.legacy_container AS container, "
    "       count(c) AS consumers, toString(j.updated_at) AS updated "
    "ORDER BY j.domain, j.name"
)
_Q_SUMMARY = (
    "MATCH (j:IngestSourceSpec) "
    "RETURN j.migration_status AS migration, j.source_kind AS kind, count(*) AS n"
)
_Q_KEYS = (
    "MATCH (j:IngestSourceSpec) WHERE j.nokkelref IS NOT NULL "
    "UNWIND j.nokkelref AS key "
    "RETURN key AS name, count(j) AS sources, collect(j.name)[..6] AS brukt_av "
    "ORDER BY sources DESC, name"
)


def _graph(query: str, limit: int = 200) -> list[dict]:
    url = API_BASE + "/graph/query?" + urllib.parse.urlencode(
        {"query": query, "limit": limit})
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            payload = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        # bred 502-dekning (reviewer-nit): read-timeout og ikke-JSON-kropp er
        # også "upstream utilgjengelig", ikke 500
        raise HTTPException(status_code=502, detail=f"unified API unreachable: {e}")
    return payload.get("results") or []


@router.get("/sources")
def sources():
    return {"sources": _graph(_Q_SOURCES)}


@router.get("/keys")
def keys():
    """Nøkkel-NAVN + referanser fra registeret (D5: verdier finnes KUN som filer
    i .11-storen — aldri i graf, API eller GUI; her vises bare navn/spredning)."""
    return {"keys": _graph(_Q_KEYS)}


@router.get("/summary")
def summary():
    rows = _graph(_Q_SUMMARY)
    by_migration: dict = {}
    by_kind: dict = {}
    total = 0
    for r in rows:
        n = int(r.get("n") or 0)
        total += n
        by_migration[r.get("migration") or "?"] = by_migration.get(r.get("migration") or "?", 0) + n
        by_kind[r.get("kind") or "?"] = by_kind.get(r.get("kind") or "?", 0) + n
    return {"total": total, "by_migration": by_migration, "by_kind": by_kind}


# ── SKRIVE-flater (BL-2354): GUI-en er creds-fri — register-mutasjoner proxes til
# unified-API-ets validerte skriveport (.12 /jetstream/registry/*, D4 håndhevet
# server-side DER), nøkkel-set går via forced-command-ssh til .11 (kanalen kan
# BARE 'set NAVN' og 'list' — get/rm nektes av authorized_keys-tvangen; verdier
# kan gå inn, aldri ut). Alle ruter arver dashboardets sesjons-auth.

import subprocess

from pydantic import BaseModel

_SSH_KEYCHANNEL = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                   "-i", os.path.expanduser("~/.ssh/id_ed25519_jetstream"),
                   "mnemosyne@192.168.40.11"]
KEYNAME_RE = __import__("re").compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def _proxy_post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        API_BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise HTTPException(status_code=e.code, detail=detail)
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(status_code=502, detail=f"skriveporten utilgjengelig: {e}")


class SourceIn(BaseModel):
    name: str
    source_kind: str
    domain: str = "general"
    endpoint_hint: str | None = None
    cadence_minutes: int = 60
    parser: str | None = None
    nokkelref: list[str] = []


@router.post("/sources")
def add_source(s: SourceIn):
    return _proxy_post("/jetstream/registry/source",
                       s.model_dump() | {"proposed_by": "env-gui"})


class ConsumerIn(BaseModel):
    source: str
    consumer: str


@router.post("/consumer")
def declare_consumer(c: ConsumerIn):
    return _proxy_post("/jetstream/registry/consumer", c.model_dump())


class MigrationIn(BaseModel):
    source: str
    status: str


@router.post("/migration")
def set_migration(m: MigrationIn):
    return _proxy_post("/jetstream/registry/migration", m.model_dump())


class KeyIn(BaseModel):
    value: str


@router.put("/keys/{name}")
def set_key(name: str, k: KeyIn):
    """WRITE-ONLY nøkkel-set: verdien pipes rett til .11-storen via tvangs-
    kanalen og finnes aldri i logg/graf/respons — kun fingeravtrykk returneres."""
    if not KEYNAME_RE.match(name):
        raise HTTPException(422, f"ugyldig nøkkelnavn: {name!r}")
    if not k.value.strip():
        raise HTTPException(422, "tom verdi")
    try:
        r = subprocess.run(_SSH_KEYCHANNEL + [f"set {name}"],
                           input=k.value.strip().encode(),
                           capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        raise HTTPException(502, "nøkkelkanalen svarte ikke")
    if r.returncode != 0:
        raise HTTPException(502, f"nøkkelkanal-feil: {r.stderr[:120].decode('utf-8','replace')}")
    return {"ok": True, "detail": r.stderr.decode("utf-8", "replace").strip()[:120]}


@router.get("/keystore")
def keystore():
    """Store-status fra .11 via kanalen: navn+fingeravtrykk+dato — aldri verdier."""
    try:
        r = subprocess.run(_SSH_KEYCHANNEL + ["list"],
                           capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise HTTPException(502, "nøkkelkanalen svarte ikke")
    if r.returncode != 0:
        raise HTTPException(502, "keystore utilgjengelig")
    rows = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 3:
            rows.append({"name": parts[0], "fingerprint": parts[1], "mtime": parts[2]})
    return {"keys": rows}
