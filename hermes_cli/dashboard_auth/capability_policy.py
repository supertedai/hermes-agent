"""Kapabilitets-policy: hvem ser hvilke skills (BL-3428 / ADR-045, ADR-044 D4).

HVORFOR DENNE FINNES
--------------------
BL-3404 ga Symbiose multiuser. Identiteten er skilt per bruker — men KAPABILITETEN
var det ikke: bruker nummer to fikk de samme 115 skillene som Morten, inkludert
``symbiose/flyby`` (skriver kandidater inn i grafen) og de 28 ``opus``-skillene som
er governance-verktøy for eieren. Samme klasse som ``RESERVED_USERNAMES``/BL-2790
verner mot på identitets-siden, uten noen tilsvarende gate på evne-siden.

TO SPØRSMÅL, TO HJEM (ADR-045 D1 vs. Mortens «jeg må kunne styre dette i backend»)
---------------------------------------------------------------------------------
ADR-045 D1 sier at erklæringen skal bo i artefaktet selv, ikke i en sentral tabell
som kan drive fra det den beskriver. Morten vil styre fra ``/brukere``. Det er ikke
i konflikt, fordi det er TO forskjellige spørsmål:

  * HVA ER ARTEFAKTET?  →  bor i skillen (``metadata.hermes.visibility`` i
    SKILL.md-frontmatteren). En skills natur følger skillen, og overlever en
    flytting av butikken.
  * HVEM FÅR DET?       →  bor hos BRUKEREN (users.json). En tildeling handler om
    en person, ikke om et verktøy, og hører hjemme der identiteten bor.

Klassifiseringen Morten gjør i ``/brukere`` er et tredje, mellomliggende lag: en
KATEGORI-default for de 113 skillene som ikke erklærer noe selv. Presedens:
  frontmatter  >  kategori-klassifisering  >  DEFAULT_VISIBILITY
Den dagen en skill får frontmatter, slutter kategori-defaulten å gjelde for den —
artefaktet vinner, som ADR-045 D1 krever.

ADR-044 D4-KOHERENS
-------------------
ADR-044 slo fast at skills er LOKALE for Hermes («verktøy, ikke minne»). Denne
policyen flytter dem ikke inn i veven. Den er heller ikke et minne: den er en
tilgangsliste, og den bor i samme fil som identiteten den gjelder for
(``users.json``, 0600, samme atomiske skrive-disiplin). Grensen fra ADR-044 D4
står — det er bare eierskapet innenfor Hermes som får en akse.
ADR-044s premiss om «19 skills» er korrigert til 115 i ADR-045 §1.

FAIL-CLOSED (ADR-045 D2)
------------------------
Default er ``owner``, ikke ``system``. «Vi rakk ikke å klassifisere den» skal aldri
bety «alle ser den». En ukjent bruker, en bruker uten policy, eller en policy som
ikke lar seg lese, gir det MINSTE settet — aldri det største.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

# Aksene fra ADR-045 D1. "steward:<navn>" behandles som owner inntil
# steward-aksen bindes (ADR-045 §6 spørsmål 3 — Mortens valg).
VIS_SYSTEM = "system"    # lik for alle innloggede
VIS_OWNER = "owner"      # kun Morten (eller den som har fått den eksplisitt)
DEFAULT_VISIBILITY = VIS_OWNER          # ADR-045 D2: fail-closed
_VIS_RE = re.compile(r"^(system|owner|steward:[a-z0-9_.-]{1,40})$")

# Kategorier Symbiose selv skriver. De er governance-verktøy for eieren, og
# klassifiseres som owner uten videre vurdering (ADR-045 D2).
SYMBIOSE_OWNED = ("opus", "symbiose")


# B1 (reviewer, KRITISK): butikken og skills-treet må resolveres FORSKJELLIG.
#
# Målt: dashboardet kjører med HERMES_HOME=~/.hermes-gui (users.json + 115
# skills), mens gatewayen som HÅNDHEVER kjører med HERMES_HOME=~/.hermes
# (93 skills, INGEN users.json). Begge resolverte ambient ved kalltidspunkt.
# Rullet ut som først skrevet ville gaten sett en tom butikk, gjort ALLE til
# ukjent bruker, og skjult alle 93 skillene fra Morten.
#
# Riktig splitt:
#   BUTIKKEN (hvem er du, hva har du fått)  → KANONISK, én sti for alle
#     prosesser. En autorisasjonsavgjørelse kan ikke henge på en
#     kontekst-overstyrbar sti (hermes_constants har _HERMES_HOME_OVERRIDE
#     som ContextVar med per-task-profiler).
#   SKILLS-TREET (hva finnes å skjule)      → LOKALT for den som spør. Gaten
#     returnerer skill-NAVN, og må navngi de skillene runtimen faktisk har.
#     De to hjemmene har drevet 22 skills fra hverandre (ADR-045 §1).

CANONICAL_HOME_ENV = "SYMBIOSE_USERS_HOME"
_CANONICAL_DEFAULT = "~/.hermes-gui"


def canonical_users_path() -> Path:
    """users.json — samme fil uansett hvilken prosess som spør."""
    return (Path(os.environ.get(CANONICAL_HOME_ENV) or _CANONICAL_DEFAULT)
            .expanduser() / "users.json")


def skills_root(home: Optional[Path] = None) -> Path:
    if home is not None:
        return Path(home) / "skills"
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env).expanduser() / "skills"
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home() / "skills"
    except Exception:
        return Path.home() / ".hermes-gui" / "skills"


def _declared_visibility(skill_md: Path) -> str:
    """``metadata.hermes.visibility`` fra SKILL.md, eller "" hvis den ikke sier noe.

    Leser de første ~40 linjene som tekst i stedet for å YAML-parse: frontmatteren
    er allerede lest av Hermes selv ved hver kategori-oppslag, og denne stien kalles
    per innlogget tur. En tredjeparts-YAML-parser her ville lagt en avhengighet inn
    i en auth-nær sti for å hente ett felt.
    """
    try:
        with skill_md.open(encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 40:
                    break
                m = re.match(r"^\s*visibility\s*:\s*[\"']?([a-z0-9_.:-]+)[\"']?\s*$", line)
                if m and _VIS_RE.match(m.group(1)):
                    return m.group(1)
    except OSError:
        pass
    return ""


# C2 (reviewer, MÅLT): første cache nøklet på ROT-katalogens mtime. En skill
# lagt til under en EKSISTERENDE kategori endrer ikke roten — den ble derfor
# aldri sett, aldri lagt i `all_skills`, og dermed ALDRI SKJULT. En helt ny,
# uklassifisert skill er nøyaktig det DEFAULT_VISIBILITY = owner finnes for;
# cachen inverterte den stille til fail-OPEN. Frontmatter-endringer ble heller
# aldri fanget (å redigere en fil endrer ikke foreldrekatalogens mtime), så
# ADR-045 D1 «artefaktet vinner» sluttet å virke etter første skann.
#
# TTL i stedet for mtime: den binder utdatertheten til et tall vi velger, i
# stedet for til en hendelse vi ikke klarer å observere. 10 s holder de ~115
# kallene i én prompt varme (målt 0,00 ms) og gjør en ny skill synlig for
# gaten innen ti sekunder.
_INV_TTL_S = 10.0
_INV_CACHE: tuple = ()      # (sti, utloeper_ts, verdi) — settes ATOMISK


def _scan(home: Optional[Path]) -> dict:
    """Rå katalog-skann, cachet på (sti, mtime).

    (d) (reviewer, MÅLT): uten dette gjorde `disabled_for` TO fulle skann —
    ett i `visible_skills`, ett for `all_skills` — altså 232 filåpninger per
    kall, i en funksjon som ligger i prompt-stien. Nå: ett skann, cachet.
    Se C2-notatet over for hvorfor nøkkelen er TTL og ikke mtime.
    """
    global _INV_CACHE
    root = skills_root(home)
    now = time.monotonic()
    hit = _INV_CACHE
    # Ett felt, ikke to (reviewer): «nøkkel» og «verdi» ble satt i to steg uten
    # lås, og FastAPI kjører sync-endepunkter i en threadpool — en samtidig
    # leser kunne få NY nøkkel med GAMMEL verdi. En tuple byttes atomisk.
    if len(hit) == 3 and hit[0] == str(root) and hit[1] > now:
        return hit[2]
    cats: dict = {}
    if root.is_dir():
        for md in sorted(root.rglob("SKILL.md")):
            try:
                rel = md.relative_to(root)
            except ValueError:
                continue
            cat = rel.parts[0] if len(rel.parts) > 1 else "(rot)"
            c = cats.setdefault(cat, {"skills": [], "declared": {}})
            c["skills"].append(md.parent.name)
            vis = _declared_visibility(md)
            if vis:
                c["declared"][md.parent.name] = vis
    _INV_CACHE = (str(root), now + _INV_TTL_S, cats)
    return cats


def inventory(home: Optional[Path] = None, policy: Optional[dict] = None) -> list:
    """Skill-katalogen slik admin-flaten skal se den.

    Én rad per KATEGORI (det er granulariteten Morten styrer på — 115 rader ville
    vært en liste ingen leser). ``declared`` teller skills som erklærer seg selv;
    de er unndratt kategori-klassifiseringen.
    """
    cats = _scan(home)
    pol = (policy or {}).get("categories") or {}
    out = []
    for cat, c in sorted(cats.items()):
        classified = pol.get(cat)
        out.append({
            "category": cat,
            "count": len(c["skills"]),
            # Hva kategorien er klassifisert som av Morten (tom = ikke tatt stilling)
            "classification": classified if _VIS_RE.match(str(classified or "")) else "",
            # Hva den EFFEKTIVT blir uten klassifisering
            "effective_default": (VIS_OWNER if cat in SYMBIOSE_OWNED
                                  else DEFAULT_VISIBILITY),
            "symbiose_owned": cat in SYMBIOSE_OWNED,
            # Skills som overstyrer kategorien selv (ADR-045 D1: artefaktet vinner)
            "declared": c["declared"],
            "skills": sorted(c["skills"]),
        })
    return out


def _visibility_of(cat: str, skill: str, cat_declared: dict, policy: dict) -> str:
    """Presedens: frontmatter > kategori-klassifisering > default."""
    d = cat_declared.get(skill)
    if d and _VIS_RE.match(d):
        return d
    c = ((policy or {}).get("categories") or {}).get(cat)
    if c and _VIS_RE.match(str(c)):
        return str(c)
    return VIS_OWNER if cat in SYMBIOSE_OWNED else DEFAULT_VISIBILITY


def visible_skills(username: str, *, is_owner: bool, granted: Optional[list] = None,
                   home: Optional[Path] = None, policy: Optional[dict] = None) -> set:
    """Skill-navn denne prinsipalen SKAL se."""
    # (e) (reviewer): ETT flatt navnerom for to ting er en latent bombe —
    # fire skill-navn er også kategori-navn (computer-use, dogfood,
    # hermes-desktop-plugins, yuanbao). I dag er de 1:1, så en tildeling gir
    # samme resultat. Legges det en skill nr. 2 i kategorien, ville en
    # tildeling som var ment som «den ene skillen» plutselig gitt HELE
    # kategorien — uten at tildelingen ble rørt. Prefikset nå, mens det ikke
    # finnes tildelinger i drift. Bart navn = kategori (dagens betydning).
    cats_granted, skills_granted = set(), set()
    for g in (granted or []):
        g = str(g).strip()
        if g.startswith("skill:"):
            skills_granted.add(g[6:])
        elif g.startswith("cat:"):
            cats_granted.add(g[4:])
        elif g:
            cats_granted.add(g)
    out = set()
    for row in inventory(home, policy):
        cat = row["category"]
        for skill in row["skills"]:
            vis = _visibility_of(cat, skill, row["declared"], policy or {})
            if vis == VIS_SYSTEM or is_owner:
                out.add(skill)                     # system, eller eieren
            elif cat in cats_granted or skill in skills_granted:
                out.add(skill)                     # eksplisitt tildelt av Morten
    return out


def disabled_for(username: str, *, is_owner: bool, granted: Optional[list] = None,
                 home: Optional[Path] = None, policy: Optional[dict] = None) -> set:
    """Komplementet: skill-navn som skal SKJULES for denne prinsipalen.

    Runtime-gaten (``agent.skill_utils.get_disabled_skill_names``) er formet som et
    DISABLED-sett, så policyen leveres i den formen i stedet for at gaten må snus.
    Å snu en fungerende auth-gate for å passe en ny konsument er hvordan man lager
    hull; å levere i gatens eget format er hvordan man lar den fortsette å virke.
    """
    allowed = visible_skills(username, is_owner=is_owner, granted=granted,
                             home=home, policy=policy)
    all_skills = set()
    for names in _scan(home).values():          # cachet — ikke et andre skann
        all_skills.update(names["skills"])
    return all_skills - allowed
