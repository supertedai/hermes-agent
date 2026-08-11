"""lease_authority.py — steg 6 «claim_and_lease»: leasen KAN tas, ikke bare kreves. BL-4059.

## STATUS, FØRST, FORDI DEN ER LETT Å LESE FEIL

**Skrivesiden er BYGGET, ikke KOBLET.** Ingenting kaller `claim`, `release` eller
`held_lease` ennå. Den eneste importen er `faber_observe`, som henter `check` og
`scope_paths` — lesesiden, som bare er flyttet hit.

Så etter denne modulen TAR steg 6 fortsatt ikke leasen, og
`faber_control_bridge.py:30`s «Steg 6 (claim/lease) … rapporteres som
`NOT_EXECUTED`» er FORTSATT RIKTIG. Ikke flipp den til utført fordi mekanismen
finnes: det ville vært en skrevet status uten en handling bak — nøyaktig
fabrikkeringen denne BL-en finnes for å fjerne.

Innkoblingen er **BL-4062**: `GovernedCodeRunner` tar leasen på steg 6, og steg 11
(+ `faber_runtime.build_callable`) slutter å lese lease-settet fra produsenten.
Utsatt fordi `agent/code_workflow.py` bar ~950 ulandede linjer fra parallelle
sesjoner (steg 8/11/12/13) da dette ble skrevet.

## Hva som var målt

Leasen ble KREVD to steder og TATT ingen steder:

    agent/code_workflow.py:338   PreflightGate.REQUIRED_REFS = ("git", "lease")
    agent/code_workflow.py:347   if not evidence.lease_clear: "target lease is not clear"
    agent/code_workflow.py:891   LandingScopeGate: landingssett ⊆ lease-sett
    (ingen kaller)               work_lease claim

De to `claim`-treffene i repoet var `execution_ledger.claim()` (idempotens) og
`stream_single_writer` — begge urelaterte. `faber_control_bridge.py:30` innrømmet
det selv: «Steg 6 (claim/lease) … rapporteres som NOT_EXECUTED.»

## Hvorfor det er den samme feilen som startet hele arbeidet

BL-4003 diagnostiserte at preflight-gaten krevde artefakter workflowen produserte
SENERE — en sirkel som bare kunne brytes ved å SKRIVE en status, altså fabrikkere
evidens. Reviewer blokkerte nøyaktig det i `cab10c5f9`. Her var samme form ett lag
opp: gaten krevde en lease kjeden aldri tok, så den eneste veien gjennom var å
skrive `lease_ref` i `goals.json`.

**En gate som bare kan passeres ved å fabrikkere evidens, lærer bort fabrikkering.**

## Den andre halvdelen, som er lettere å overse

Selv med en ekte lease hentet steg 11 lease-settet sitt herfra:

    lease_set = tuple(str(preflight.evidence.source_refs.get("lease", "")).split(","))

`source_refs["lease"]` er `evidence["lease_ref"]` fra `goals.json` — produsentens
egen streng. Sjekken «landingssett ⊆ lease-sett» sammenlignet altså en MÅLT mengde
mot en PÅSTÅTT mengde, og en produsent som skrev tre filnavn hadde dermed lov til å
lande tre filer. **Derfor er kontrakten her at lease-settet nedstrøms er
autoritetens `acquired`-liste — aldri produsentens referanse.** Halvparten av
jobben var å ta leasen; den andre halvparten er å gjøre den til kilden.

## Hvorfor autoriteten, og ikke `work_lease` direkte

`.15` har ingen graf-kreditiv (ADR-061). `work_lease.py` er en ren Neo4j-klient og
bor på `.13`. Ruten `/surface/lease/{claim,release,check}` (`61d6fa6d4`,
`cae1a5566`) utleder eieren av TOKENET — kalleren kan ikke oppgi den — og
`surface:`-prefikset er reservert i `work_lease._session_id()` slik at en
CLI-bruker ikke kan minte en byte-identisk eier. Denne modulen bygger ingen ny
autoritet; den bruker den som finnes.

## To målte begrensninger, skrevet ned framfor skjult

**1. Eieren er per PRINCIPAL, ikke per KJØRING.** Autoriteten avleder
`surface:<principal>`, så to samtidige Faber-kjøringer på `.15` er samme eier for
lease-laget: de blokkerer ikke hverandre, og den enes `release` frigjør den andres
lease. Leasen verner altså mot ANDRE prinsipaler, ikke mot en søsken-kjøring. Å
fikse det krever et server-generert lease-token (kaller-oppgitt kjørings-id ville
vært forfalskbart — jf. `surface:`-reservasjonen), altså en endring i autoriteten
på `.13`. Det er ikke gjort her, og steg 6 later ikke som noe annet.

**2. `scope_paths` leste bare `.py` — UTVIDET I BL-4070 (D2).** Begrensningen sa
at en endring hørte hjemme begge steder samtidig. Den betingelsen er nå oppfylt
ved konstruksjon: `faber_observe` importerer denne funksjonen i stedet for å ha
sin egen (BL-4059), og `faber_control_bridge._paths_from_scope` delegerer hit
(BL-4070). Det finnes ÉN parser, så `check` og `claim` kan ikke se ulike sett.
Målt før fiksen: broen leste to filer der denne leste null, og steg 6 meldte
«scope navngir ingen filer» som om det var et svar om leasen.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

_log = logging.getLogger(__name__)

#: Autoritetsruten. Samme verdi `faber_observe` alltid har brukt for `check`;
#: claim og check MÅ peke på samme instans, ellers sjekker vi én graf og skriver
#: til en annen.
SURFACE_API = os.environ.get("SURFACE_API_URL", "http://192.168.40.12:8010")

#: CLAUDE.md: «--ttl 3600 når arbeidet har reviewer-runder. Default er 1800s, og
#: en lease som utløper midt i jobben gjør commiten uattribuerbar.» Steg 6 sitter
#: foran steg 10 (canonical_reviewer_gate) per definisjon, så 3600 er ikke et valg
#: her — det er den eneste verdien som dekker kjeden den åpner.
DEFAULT_TTL = 3600

#: `LeaseRequest.paths` på autoriteten er `min_length=1, max_length=50`.
MAX_PATHS_PER_CALL = 50

#: Klientens hemmelighet leses fra FIL, ikke bare env: cron-linja på `.15` setter
#: kun HERMES_HOME og leser ingen .env.
_TOKEN_FILE = os.environ.get(
    "SURFACE_RECEIPT_TOKEN_FILE",
    str(Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes-gui")))
        / ".surface_receipt_token"))


def surface_token() -> str:
    """Env først (test), så fil. Fila MÅ være 0600 og eid av oss.

    Feil modus gir TOM token — altså «uverifisert» — framfor å bruke en
    hemmelighet andre kan lese.

    **Og tom token betyr her IKKE «gå videre uten lease».** Det var hullet
    `_resolve_lease_clear` måtte lukke på lesesiden: produsenten eier denne fila,
    så `chmod 0644` slo av verifiseringen, og kontrollen falt tilbake på
    produsentens egen påstand. Skrivesiden arver samme regel — se :func:`claim`,
    som returnerer «ikke tatt» og aldri «antatt tatt».
    """
    env = os.environ.get("SURFACE_RECEIPT_TOKEN", "").strip()
    if env:
        return env
    try:
        f = Path(_TOKEN_FILE)
        if not f.exists() or f.is_symlink():
            return ""
        st = f.stat()
        if st.st_mode & 0o077 or st.st_uid != os.getuid():
            return ""
        return f.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


#: Filformene et `repo_scope` kan navngi. UTVIDET FRA `.py` I BL-4070 (D2).
#:
#: `faber_control_bridge._paths_from_scope` bar allerede denne formen, og de to
#: parserne var UENIGE: samme streng ga to filer hos broen og «scope navngir
#: ingen filer» her. Skaden var ikke at lease-gaten ble vakuøs — `LandingScopeGate`
#: feiler lukket på tomt lease-sett — men at steg 6 ikke KUNNE oppdage en ekte
#: konflikt for et scope som navnga en `.service`-enhet eller en `.md`, og
#: rapporterte det som et svar. «Ingen filer å spørre om» og «ingen konflikt» er
#: ikke det samme, og en parser som gjør dem like produserer falske grønne.
#:
#: Modulens begrensning 2 sa at en utvidelse hører hjemme begge steder samtidig.
#: Det er oppfylt ved konstruksjon nå: `faber_observe` importerer denne
#: funksjonen (BL-4059), og broen delegerer hit fra BL-4070. Det finnes ÉN
#: parser, så de kan ikke divergere igjen.
#:
#: TO KONSEKVENSER SOM IKKE FULGTE AV D2-BEGRUNNELSEN, NAVNGITT (reviewer NB3):
#: 1. I `faber_observe._resolve_lease_clear` ga et ikke-`.py`-scope FOER dette
#:    hardt `False` («scope lister ingen filer»). Naa blir det et EKTE
#:    autoritetssvar som kan vaere `True`. Det er en bevisst LOESNING av
#:    `*/20`-preflighten — riktig, fordi et scope som navngir en `.service`
#:    alltid var et sporsmaal ingen stilte, ikke et nei.
#: 2. Moensteret er ANKRET (`^...$`), saa det er ogsaa en INNSNEVRING: en
#:    `.py`-sti med et tegn utenfor `[\\w./-]` faller naa ut der
#:    `endswith('.py')` beholdt den. Maalt mot flaatens sju ekte mål: null
#:    endring. Utvidelsen er en LISTE, ikke «alt».
_SCOPE_PATH = re.compile(r"^[\w./-]+\.(?:py|ts|tsx|js|json|ya?ml|md|sh|service|plist)$")


def scope_paths(repo_scope: str) -> list[str]:
    """Trekk ut filstier fra et `repo_scope` som ``"hermes-agent: a.py, b.py"``.

    Autoriteten selv har ingen filtype-begrensning — den holder lease på hva som
    helst. Filteret her er kallersidens, og det er nå det samme filteret overalt;
    se :data:`_SCOPE_PATH`.
    """
    tail = repo_scope.split(":", 1)[1] if ":" in repo_scope else repo_scope
    out: list[str] = []
    for frag in re.split(r"[,\s]+", tail):
        frag = frag.strip().strip(".,;")
        if frag and _SCOPE_PATH.match(frag):
            out.append(frag)
    return out


@dataclass(frozen=True)
class LeaseOutcome:
    """Resultatet av å FORSØKE å ta en lease.

    ``acquired`` er autoritetens svar, ikke det vi ba om. Det skillet er hele
    poenget: nedstrøms (steg 11) sammenlignes landingssettet mot DETTE, og en
    liste vi selv fant på ville gjenopprettet påstanden vi nettopp fjernet.
    """

    ok: bool
    acquired: tuple[str, ...]
    reason: str
    #: Stier autoriteten IKKE klarte å frigjøre etter et delvis claim. Er denne
    #: ikke-tom er en lease foreldreløs til TTL — se :func:`claim`.
    still_held: tuple[str, ...] = ()
    #: (sti, eier) for stier en ANNEN prinsipal holder.
    blocked_by: tuple[tuple[str, str], ...] = ()
    owner: str = ""
    ref: str = ""

    @property
    def lease_set(self) -> tuple[str, ...]:
        """Settet nedstrøms har lov til å lande innenfor. Tomt når intet er tatt."""
        return self.acquired if self.ok else ()


def _clean(paths: Sequence[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for p in paths:
        s = str(p).strip()
        if s and s not in seen:
            seen.append(s)
    return tuple(seen)


def _request(method: str, path: str, token: str, *,
             payload: Any = None, params: dict[str, str] | None = None,
             timeout: float = 10.0) -> tuple[int, Any, str]:
    """Ett HTTP-kall mot autoriteten. Returnerer ``(status, body, transportfeil)``.

    ``status`` er 0 når kallet aldri nådde fram; da er ``body`` None og
    tredjeverdien forklarer hvorfor. En HTTP-feilkode er IKKE en transportfeil —
    kroppen leses uansett, fordi 409 fra `/lease/claim` bærer den eneste
    opplysningen som betyr noe (`STILL_HELD`).

    **Vi sender aldri et eier-/sesjonsfelt.** Eieren utledes av tokenet på
    serveren; å tilby et felt her ville gjenåpnet nøyaktig navnerommet
    `work_lease._session_id()` reserverer bort.
    """
    url = f"{SURFACE_API}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None
    headers = {"X-Surface-Token": token}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null"), ""
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"null")
        except Exception:  # noqa: BLE001
            body = None
        return exc.code, body, ""
    except Exception as exc:  # noqa: BLE001
        return 0, None, f"{type(exc).__name__}: {exc}"


def check(paths: Sequence[str]) -> tuple[bool | None, str]:
    """Spør autoriteten om leasen. Returnerer ``(clear, note)``.

    ``None`` betyr IKKE VERIFISERT — en tredje verdi med vilje. ``False`` ville
    sagt «ingen lease finnes», som er en påstand vi ikke har grunnlag for når vi
    ikke fikk spurt. Kalleren avgjør hva uverifisert skal bety; se
    `faber_observe._resolve_lease_clear`, der det betyr BLOKKER.
    """
    wanted = _clean(paths)
    if not wanted:
        return None, "ingen stier å sjekke"
    token = surface_token()
    if not token:
        return None, (f"ingen token ({_TOKEN_FILE} mangler eller har feil modus) — "
                      f"lease er UVERIFISERT, ikke fraværende")
    status, body, transport = _request("GET", "/surface/lease/check", token,
                                       params={"paths": ",".join(wanted)}, timeout=8.0)
    if transport:
        return None, f"autoriteten unåbar ({transport}) — UVERIFISERT"
    if status != 200 or not isinstance(body, dict):
        return None, f"autoriteten svarte {status} — UVERIFISERT"
    return bool(body.get("lease_clear")), (
        f"autoritet: {len(body.get('held_by_me') or [])} av {len(wanted)} eid, "
        f"{len(body.get('held_by_others') or [])} hos andre")


def claim(paths: Sequence[str], *, ttl: int = DEFAULT_TTL, note: str = "") -> LeaseOutcome:
    """Ta lease på `paths`. Steg 6.

    Kontrakten er streng med vilje, og hver linje i den er en felle noen alt har
    gått i:

    * **Tomt sett er ikke «trivielt tatt».** Det er UKJENT, og en ukjent mengde kan
      ikke være en delmengde av noe (samme regel som `LandingScopeGate` på steg 11).
    * **Ingen token → ikke tatt.** Ikke «antatt tatt». Se :func:`surface_token`.
    * **Autoriteten unåbar → ikke tatt.** Fravær av svar er ikke et svar.
    * **200 er ikke suksess i seg selv.** Vi leser `acquired` og sammenligner med
      det vi ba om. Serveren returnerer `acquired` fordi `work_lease.claim()` gir
      en EXIT-KODE, ikke `(ok, broke, blocked)` — den som leser lokale variabler
      framfor `return` slutter feil om hva som ble tatt. Klienten arver forsiktig-
      heten: vi slutter ingenting fra statuskoden alene.
    * **Delvis er ikke tatt, OG delvis må kompenseres.** Et 409 midt i et fler-fil-
      claim etterlater foreldreløse leases — noen er allerede tatt. Serveren
      kompenserer på sin egen 409-sti; blir svaret 200 med et ufullstendig
      `acquired`, gjør vi det samme her, med samme policy. Feiler kompenseringen,
      meldes `STILL_HELD` HØYLYTT (ERROR + i utfallet), ellers har vi byttet en
      stille foreldreløs lease mot en litt mindre stille.

    Ett tilfelle kompenseres bevisst IKKE: transportfeil. Da vet vi ikke om
    serveren rakk å skrive, og `release` er destruktiv for en søsken-kjøring med
    samme prinsipal (begrensning 1 i modul-docstringen). Vi rapporterer UKJENT med
    stinavn og TTL framfor å ta en handling vi ikke har grunnlag for.
    """
    wanted = _clean(paths)
    if not wanted:
        return LeaseOutcome(False, (), "ingen stier å lease — et tomt sett er ukjent, "
                                       "ikke klarert")
    if len(wanted) > MAX_PATHS_PER_CALL:
        # Autoriteten svarer 422 på over 50 stier. Uten denne grenen ble den
        # feilen til «autoriteten svarte 422», som er fail-closed, men umulig å
        # diagnostisere. Vi deler IKKE opp i flere kall: et oppdelt claim er ikke
        # atomisk, og et delvis resultat på tvers av bolker er nøyaktig den
        # foreldreløse tilstanden felle 3 handler om.
        return LeaseOutcome(
            False, (),
            f"{len(wanted)} stier i scope, men autoriteten tar maks "
            f"{MAX_PATHS_PER_CALL} per kall — del opp arbeidet, ikke leasen "
            f"(et oppdelt claim er ikke atomisk)")
    token = surface_token()
    if not token:
        return LeaseOutcome(False, (), f"ingen token ({_TOKEN_FILE} mangler eller har "
                                       f"feil modus) — leasen er IKKE tatt")

    status, body, transport = _request(
        "POST", "/surface/lease/claim", token,
        payload={"paths": list(wanted), "ttl": int(ttl), "note": note})

    if transport or status >= 500:
        # SAMME FARE, SÅ SAMME BEHANDLING. En transportfeil og en 5xx er ikke to
        # ting her: begge lar spørsmålet «rakk autoriteten å skrive?» stå åpent.
        # 502-en er ikke hypotetisk — den er lesbar i ruten:
        #
        #   surface_receipt.py:399  rc = _claim(...)      # SKRIVER leasene
        #   surface_receipt.py:405  held = _neo4j(...)    # tilbakelesing, SAMME try
        #   surface_receipt.py:409  except: HTTPException(502)   # INGEN release
        #
        # Feiler tilbakelesingen, er leasene tatt og ruten svarer 502 uten den
        # kompenseringen dens EGEN 409-sti gjør. Å kalle det «leasen er IKKE tatt»
        # ville vært en påstand vi ikke har grunnlag for — den samme formen for
        # ugrunnet påstand hele dette arbeidet handler om.
        why = transport or f"autoriteten svarte {status}"
        _log.error("steg 6: claim mot %s feilet (%s) for %s — UKJENT om autoriteten "
                   "rakk å skrive; en lease kan være foreldreløs i inntil %ss. Ingen "
                   "kompenserende release: den ville også kunne frigjøre en "
                   "søsken-kjørings lease (samme prinsipal = samme eier).",
                   SURFACE_API, why, ", ".join(wanted), ttl)
        return LeaseOutcome(False, (), f"{why} — UKJENT om leasen ble tatt; den er "
                                       f"ikke vår å bygge på, og kan stå til TTL")

    if status == 409:
        detail = body.get("detail") if isinstance(body, dict) else None
        detail = detail if isinstance(detail, dict) else {}
        still = _clean(detail.get("STILL_HELD") or ())
        blocked = tuple(
            (str(b.get("path", "")), str(b.get("holder", "")))
            for b in (detail.get("blocked") or []) if isinstance(b, dict))
        if still:
            _log.error("steg 6: autoriteten klarte IKKE å rulle tilbake %s (ref %s) — "
                       "disse er leaset uten en intensjon bak, i inntil %ss.",
                       ", ".join(still), detail.get("ref", "?"), ttl)
        # `no_lease_written` er den ANDRE grunnen til 409, og serveren oppgir den
        # eksplisitt. Kastet vi den, sto operatøren igjen med «ingen oppgitt» på et
        # avslag serveren nettopp forklarte.
        no_write = _clean(detail.get("no_lease_written") or ())
        why = "; ".join(f"{p} hos {h}" for p, h in blocked)
        if no_write:
            why = (why + "; " if why else "") + f"ingen lease skrevet for: {', '.join(no_write)}"
        return LeaseOutcome(
            False, (),
            f"kunne ikke ta hele settet ({why or 'ingen grunn oppgitt'})"
            + (f" — STILL_HELD: {', '.join(still)}" if still else ""),
            still_held=still, blocked_by=blocked, ref=str(detail.get("ref", "")))

    if status != 200 or not isinstance(body, dict):
        return LeaseOutcome(False, (), f"autoriteten svarte {status} — leasen er IKKE tatt")

    acquired = _clean(body.get("acquired") or ())
    owner = str(body.get("owner", ""))
    if set(acquired) != set(wanted):
        # Serveren skal svare 409 her. Gjør den ikke det, er den ufullstendige
        # leasen fortsatt vår — og en delvis lease er ikke en lease.
        missing = sorted(set(wanted) - set(acquired))
        released_ok, release_note = _release_raw(acquired, token) if acquired else (True, "")
        still = () if released_ok else acquired
        if still:
            _log.error("steg 6: 200 med ufullstendig acquired, og kompenserende release "
                       "FEILET (%s) — STILL_HELD: %s", release_note, ", ".join(still))
        return LeaseOutcome(
            False, (),
            f"autoriteten svarte 200, men tok ikke hele settet (mangler: "
            f"{', '.join(missing)}) — en delvis lease er ikke en lease",
            still_held=still, owner=owner)

    return LeaseOutcome(True, acquired, f"lease tatt av {owner} på {len(acquired)} "
                                        f"sti(er), ttl {ttl}s", owner=owner)


def _release_raw(paths: Sequence[str], token: str) -> tuple[bool, str]:
    status, body, transport = _request(
        "POST", "/surface/lease/release", token, payload={"paths": list(paths)})
    if transport:
        return False, f"transport: {transport}"
    if status != 200:
        return False, f"autoriteten svarte {status}"
    return True, "sluppet"


def release(paths: Sequence[str]) -> tuple[bool, str]:
    """Slipp EGNE leases. Kan ikke slippe en annen prinsipals — eieren er avledet."""
    wanted = _clean(paths)
    if not wanted:
        return True, "ingen stier å slippe"
    token = surface_token()
    if not token:
        return False, (f"ingen token ({_TOKEN_FILE}) — kan ikke slippe; leasen står til "
                       f"TTL")
    return _release_raw(wanted, token)


@dataclass
class LeaseHold:
    """Det :func:`held_lease` gir kalleren — utfallet PLUSS hva som skjedde etterpå.

    `LeaseOutcome` er frossen og er allerede gitt fra seg når slippet skjer, så et
    mislykket `release` kunne bare eksistere i loggen: en steg-6-kvittering ville
    stått med `ok=True` og ingen spor av at leasen aldri kom tilbake. Denne er
    mutérbar med vilje, og `release_failed` stemples i `finally`, slik at kalleren
    kan lese det ETTER blokken og journalføre det.
    """

    outcome: LeaseOutcome
    #: Tom streng = sluppet som forventet (eller ingenting å slippe).
    release_failed: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome.ok

    @property
    def acquired(self) -> tuple[str, ...]:
        return self.outcome.acquired

    @property
    def lease_set(self) -> tuple[str, ...]:
        return self.outcome.lease_set

    @property
    def reason(self) -> str:
        return self.outcome.reason

    @property
    def still_held(self) -> tuple[str, ...]:
        return self.outcome.still_held


@contextmanager
def held_lease(paths: Sequence[str], *, ttl: int = DEFAULT_TTL,
               note: str = "") -> Iterator[LeaseHold]:
    """Ta lease for et arbeid, og slipp den ALLTID etterpå.

    Gir utfallet til kalleren i stedet for å kaste: steg 6 er en GATE, og en gate
    som feiler skal gi en begrunnet BLOCK oppover i kjeden, ikke et unntak som
    `GovernedCodeRunner` fanger som «runner exception».

    Slipper kun det som faktisk ble tatt. Feiler slippet, er det HØYLYTT OG
    LESBART — se :class:`LeaseHold`. En lease vi trodde vi ga fra oss, men ikke
    gjorde, er nøyaktig den foreldreløse tilstanden felle 3 handler om.
    """
    hold = LeaseHold(claim(paths, ttl=ttl, note=note))
    try:
        yield hold
    finally:
        if hold.outcome.ok and hold.outcome.acquired:
            ok, why = release(hold.outcome.acquired)
            if not ok:
                hold.release_failed = why
                _log.error("steg 6: release FEILET (%s) for %s — leasen står til TTL "
                           "(%ss) og blokkerer andre prinsipaler i mellomtiden.",
                           why, ", ".join(hold.outcome.acquired), ttl)
