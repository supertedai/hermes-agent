"""hermes_flyby_tools — Hermes' NATIVE flyby-verktøy (BL-3246, ADR-035).

Deployeres til `.15:/home/agent/agent-layer/hermes-agent/tools/flyby_tools.py` og auto-oppdages av
`tools/registry.discover_builtin_tools` (toppnivå `registry.register`-kall). Kun stdlib.

HVORFOR EN NY FIL OG IKKE EN REDIGERING AV `symbiose_tools.py`
--------------------------------------------------------------
`symbiose_tools.py` finnes KUN på .15 — den er ikke i AGI-repoet. Å redigere den ville lagt to
kilder til sannhet på en fil ingen annen strøm kan se, og ville rørt en annen strøms flate. Denne
fila er additiv, versjonskontrollert her, og registrerer seg i det SAMME `symbiose`-toolsettet, så
den arver rollen sin uten å endre den eksisterende overflaten.

HULLET DEN LUKKER
-----------------
Flyby-skillen ba Hermes kalle `selfstate_write` — et Python-import mot et repo som ikke finnes på
.15. Det eneste native alternativet var `symbiose_write` → `/api/v1/write`, hvis `type` er
`fact|memory|ownership|identity|document`. `kind=plan` matchet ingen, falt til dokument-ruten, og
kandidaten endte som en `:Document` i `routing_quarantine` uten `key` og uten `:SelfKnowledgeFact`.
Skillens kontrakt og verktøyflaten var to ulike ting; disse to verktøyene ER kontrakten.

GRENSEN, som er gaten og ikke en mangel: `flyby_write` kan skrive KANDIDATER (`kind=plan`, key
`candidate_<slug>_<dato>` — begge utledet SERVER-side). Den allokerer ikke BL, skriver ikke til
git, og kan ikke kalle noe «landet». Serveren returnerer `verified` først etter read-back; er
`verified` fraværende eller false, er kandidaten IKKE lagret — meld det, ikke pynt på det.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from tools.registry import registry

API_BASE = os.environ.get("SYMBIOSE_API_URL", "http://192.168.40.12:8010").rstrip("/")
FLYBY_TOKEN = os.environ.get("FLYBY_WRITE_TOKEN", "")


def _req(path: str, payload: dict | None = None, timeout: int = 30) -> str:
    """POST når payload er gitt, ellers GET. Feil returneres som JSON — en handler som kaster
    ville blitt en verktøy-feil uten diagnose i chatten."""
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if FLYBY_TOKEN:
        headers["X-Flyby-Token"] = FLYBY_TOKEN
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # 4xx/5xx bærer serverens `detail` — inkludert «UVERIFISERT», som ALDRI skal presenteres
        # som en vellykket lagring. Detaljen videreformidles ordrett.
        #
        # 502 = UKJENT commit-status, ikke et kjent nei: gaten kan kaste ETTER at fakta-MERGEn
        # committet (audit-CREATE feiler, BL-2592). «Ikke lagret» ville vært like galt som
        # «lagret» — derfor skilles de to her, og modellen får beskjed om å lese etter.
        body = e.read()[:600].decode("utf-8", "replace")
        if e.code == 502:
            return json.dumps({"verified": False, "commit_status": "unknown",
                               "error": f"HTTP 502 fra {path}", "detail": body,
                               "say": "Uavklart om kandidaten landet — les etter med graph_query "
                                      "før du melder noe. Ikke gjenta skrivingen blindt."},
                              ensure_ascii=False)
        return json.dumps({"verified": False, "commit_status": "not_written",
                           "error": f"HTTP {e.code} fra {path}", "detail": body})
    except Exception as e:
        return json.dumps({"verified": False, "commit_status": "unknown",
                           "error": f"{type(e).__name__} mot {API_BASE}{path}: {e}",
                           "detail": "ukjent commit-status — les tilbake med graph_query før du "
                                     "melder noe som lagret"})


def _flyby_write(args, **kw) -> str:
    acceptance = args.get("acceptance") or []
    if isinstance(acceptance, str):          # modell-emittert streng i stedet for liste
        acceptance = [s.strip() for s in acceptance.split("\n") if s.strip()]
    payload = {
        "slug": str(args.get("slug", "")).strip().lower(),
        "problem": str(args.get("problem", "")).strip(),
        "affected": str(args.get("affected", "")).strip(),
        "hypothesis": str(args.get("hypothesis", "")).strip(),
        "acceptance": [str(a).strip() for a in acceptance if str(a).strip()],
        "gate": str(args.get("gate", "")).strip().lower(),
        "epistemic": str(args.get("epistemic", "observert")).strip().lower(),
        "dedup_checked": str(args.get("dedup_checked", "")).strip(),
        "title": str(args.get("title", "")).strip() or None,
        # `input_from` = hvem innspillet kom fra. Gatens `who` (hvem som UTFØRTE skrivingen)
        # stemples server-side og kan ikke settes herfra — ellers kunne en skriving herfra blitt
        # attributert til Morten i audit-sporet.
        "input_from": str(args.get("input_from", "morten")).strip() or "morten",
    }
    missing = [k for k in ("slug", "problem", "affected", "hypothesis", "dedup_checked")
               if not payload[k]]
    if missing or not payload["acceptance"] or payload["gate"] not in ("autonomt", "reviewer", "morten"):
        # Lokal fail-closed: en kandidat uten akseptansekriterier eller gate er nettopp den
        # fritekst-formen ADR-035 lister som feilmodus. Bounces før den når nettverket.
        return json.dumps({
            "verified": False, "error": "ufullstendig kandidat",
            "missing": missing + ([] if payload["acceptance"] else ["acceptance"])
                       + ([] if payload["gate"] in ("autonomt", "reviewer", "morten") else ["gate"]),
            "detail": "gate må være autonomt|reviewer|morten; acceptance må ha minst ett kriterium. "
                      "Kjør flyby_dedup først og send hva du søkte i som dedup_checked."},
            ensure_ascii=False)
    return _req("/api/v1/flyby/candidate", payload)


registry.register(
    name="flyby_dedup",
    toolset="symbiose",
    schema={
        "name": "flyby_dedup",
        "description": ("STEG 1 av flyby: sjekk om saken ALLEREDE finnes, før du skriver en kandidat. "
                        "Søker :BL-titler og :SelfKnowledgeFact (planer/beslutninger/observasjoner/"
                        "mønstre — ADR-ene bor der). Finner du et ekte treff: utvid den saken framfor "
                        "å lage en ny. Send det du søkte i videre som dedup_checked til flyby_write."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "søkeord, minst 3 tegn"},
            "limit": {"type": "integer", "description": "treff per lag (default 8, maks 25)"},
        }, "required": ["query"]},
    },
    handler=lambda args, **kw: _req(
        "/api/v1/flyby/dedup?" + urllib.parse.urlencode({
            "q": str(args.get("query", "")),
            "limit": args.get("limit") if isinstance(args.get("limit"), int) else 8}),
        timeout=20),
    emoji="\U0001F50E",
    max_result_size_chars=8000,
)

registry.register(
    name="flyby_write",
    toolset="symbiose",
    schema={
        "name": "flyby_write",
        "description": (
            "STEG 2 av flyby: lagre et løst innspill fra Morten som en SPORBAR KANDIDAT i grafen "
            "(:SelfKnowledgeFact, kind=plan, key=candidate_<slug>_<dato>, provenance source=flyby). "
            "Bruk når Morten peker på noe som BØR GJØRES — en idé, en bekymring, et hull — ikke når "
            "han stiller et spørsmål. Kjør flyby_dedup FØRST. "
            "GRENSEN: dette allokerer IKKE BL-nummer, skriver IKKE til git, og lander INGENTING — "
            "det er Claudes tur etterpå. Si «kandidat lagret», aldri «lagt inn i BL og git». "
            "Svaret bærer verified + commit_status: verified=true er lagret; "
            "commit_status='not_written' er IKKE lagret; commit_status='unknown' er UAVKLART — "
            "les etter med graph_query og si at det er uavklart, ikke gjett i noen retning."),
        "parameters": {"type": "object", "properties": {
            "slug": {"type": "string", "description": "kort id, a-z0-9 med underscore, f.eks. flyby_writer_mangler"},
            "problem": {"type": "string", "description": "hva som er galt eller mangler, i én setning"},
            "affected": {"type": "string", "description": "berørte komponenter/filer/agenter"},
            "hypothesis": {"type": "string", "description": "hva som antakelig må endres"},
            "acceptance": {"type": "array", "items": {"type": "string"},
                           "description": "akseptansekriterier — hvordan vi VET at den er løst (minst ett)"},
            "gate": {"type": "string", "enum": ["autonomt", "reviewer", "morten"],
                     "description": "hvem som må godkjenne; morten = hard-limit"},
            "epistemic": {"type": "string", "enum": ["observert", "delvis_verifisert", "verifisert"],
                          "description": "Mortens innspill er observert, ikke en måling"},
            "dedup_checked": {"type": "string", "description": "hva du faktisk søkte i (fra flyby_dedup)"},
            "title": {"type": "string", "description": "foreslått kort tittel"},
            "input_from": {"type": "string", "description": "hvem innspillet kom fra (default morten)"},
        }, "required": ["slug", "problem", "affected", "hypothesis", "acceptance", "gate",
                        "dedup_checked"]},
    },
    handler=_flyby_write,
    emoji="\U0001F6E9",
    max_result_size_chars=4000,
)
