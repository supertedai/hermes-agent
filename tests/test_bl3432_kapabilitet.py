"""BL-3432 / ADR-046 — kapabilitets-gaten. To feil overlevde fordi målingene
brukte FORHÅNDSEKSISTERENDE tilstand. Disse testene lager tilstanden selv.

  C1  session_identity fikk kanonisk LESEsti mens SKRIVEsiden ble stående.
      Alt virket for eksisterende sesjoner og brøt kun for NYE. Min egen
      etter-måling passerte fordi den slo opp en sid fra den gamle fila —
      forskjellen på å måle filen og å måle stien.
  C2  cachen nøklet på ROT-katalogens mtime. En skill lagt til under en
      EKSISTERENDE kategori ble aldri sett, aldri lagt i all_skills, og derfor
      ALDRI SKJULT — fail-closed-defaulten invertert stille til fail-open.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAIL = []
ok = lambda c, m: print(("  PASS  " if c else "  FAIL  ") + m) or (c or FAIL.append(m))

HOME = Path(tempfile.mkdtemp())          # «kanonisk» hjem (butikk + identitet)
RUNTIME = Path(tempfile.mkdtemp())       # runtimens EGET hjem (kun skills)
os.environ["SYMBIOSE_USERS_HOME"] = str(HOME)

from hermes_cli.dashboard_auth import capability_policy as cp   # noqa: E402
from hermes_cli.dashboard_auth import user_store as us          # noqa: E402
from hermes_cli.dashboard_auth import session_identity as si    # noqa: E402


def mkskill(root, cat, name, visibility=""):
    d = root / "skills" / cat / name
    d.mkdir(parents=True, exist_ok=True)
    fm = "---\nname: %s\n" % name
    if visibility:
        fm += "metadata:\n  hermes:\n    visibility: %s\n" % visibility
    (d / "SKILL.md").write_text(fm + "---\n\ninnhold\n", encoding="utf-8")


print("\n1) C1: en NY sesjon må resolvere — skriver og leser samme fil")
# Runtimen har et ANNET HERMES_HOME enn den kanoniske butikken. Det er
# nøyaktig topologien på .15: gatewayen i ~/.hermes, butikken i ~/.hermes-gui.
os.environ["HERMES_HOME"] = str(RUNTIME)
ok(str(si.identity_path()) == str(si.identity_path(canonical=True)),
   "skrive- og lesesti er SAMME fil (C1 — var to)")
ok(str(si.identity_path()).startswith(str(HOME)),
   "og den ligger i det kanoniske hjemmet, ikke runtimens")

us.create_user(username="morten", password="admin-passord-1", role="admin",
               path=cp.canonical_users_path())
us.create_user(username="kari", password="kari-passord-1", role="user",
               path=cp.canonical_users_path())
si.set_identity("helt-ny-sid-001", "morten")        # stemples NÅ, som gatewayen gjør
ok(si.get_identity("helt-ny-sid-001") == "morten",
   "en sesjon stemplet NÅ leses tilbake (ikke en gammel fil)")
raw = json.loads(si.identity_path().read_text())
ok("helt-ny-sid-001" in raw, "og den ligger fysisk i den kanoniske fila")

print("\n2) C1: gaten resolverer den nye sesjonen i RUNTIMENS hjem")
mkskill(RUNTIME, "verktoy", "s1")
mkskill(RUNTIME, "verktoy", "s2")
us.set_capability_policy({"verktoy": "system"}, path=cp.canonical_users_path())
ok(len(cp.inventory()) == 1 and cp.inventory()[0]["count"] == 2,
   "runtimens EGET skill-tre skannes (ikke det kanoniske hjemmets)")
ok(us.resolve_disabled_skills("morten") == set(), "admin (= owner) skjuler ingenting")
ok(us.resolve_disabled_skills("kari") == set(), "system-kategori synlig for vanlig bruker")
ok(us.resolve_disabled_skills("finnes-ikke") == set(),
   "ukjent bruker ser system-kategorien, men ikke mer")

print("\n3) C2: en NY skill i en EKSISTERENDE kategori må bli skjult")
cp._INV_TTL_S = 0.05                                  # kort TTL FØR første skann
cp._INV_CACHE = ()
us.set_capability_policy({"verktoy": "system"}, path=cp.canonical_users_path())
us.resolve_disabled_skills("kari")                    # varmer cachen
mkskill(RUNTIME, "hemmelig", "topsecret")             # ny KATEGORI (uklassifisert)
time.sleep(0.1)                                       # la TTL-en løpe ut
after = us.resolve_disabled_skills("kari")
ok("topsecret" in after, "ny uklassifisert kategori skjules for vanlig bruker")
mkskill(RUNTIME, "verktoy", "s3")                     # ny skill i EKSISTERENDE kat.
us.set_capability_policy({"verktoy": "owner"}, path=cp.canonical_users_path())
time.sleep(0.1)
after2 = us.resolve_disabled_skills("kari")
ok("s3" in after2, "ny skill i EKSISTERENDE kategori blir sett (C2 — ble usynlig før)")
ok({"s1", "s2", "s3"} <= after2, "hele kategorien skjules når den er owner")

cp._INV_TTL_S = 10.0

print("\n4) C2: frontmatter-endring fanges INNEN TTL (ADR-045 D1)")
# Kontrakten er «innen TTL», ikke «øyeblikkelig». Den gamle mtime-nøkkelen
# fanget den ALDRI — det var feilen. TTL binder utdatertheten til et tall vi
# velger; testen skal måle nettopp det, ikke noe sterkere.
cp._INV_TTL_S = 0.05
cp._INV_CACHE = ()
mkskill(RUNTIME, "hemmelig", "unntak", visibility="system")
d = us.resolve_disabled_skills("kari")
ok("unntak" not in d, "skill som ERKLÆRER system overstyrer owner-kategorien")
mkskill(RUNTIME, "hemmelig", "unntak")                # fjern erklæringen
ok("unntak" not in us.resolve_disabled_skills("kari"),
   "innenfor TTL står det gamle svaret (cachen virker)")
time.sleep(0.1)
ok("unntak" in us.resolve_disabled_skills("kari"),
   "etter TTL fanges endringen — mtime-nøkkelen fanget den ALDRI")

print("\n5) cachen er atomisk og holder ytelsen")
cp._INV_TTL_S = 10.0
cp._INV_CACHE = ()
cp._scan(None)
ok(len(cp._INV_CACHE) == 3, "cachen er ÉN tuple (nøkkel+utløp+verdi), ikke to felt")
t0 = time.perf_counter()
for _ in range(200):
    us.resolve_disabled_skills("kari")
ms = (time.perf_counter() - t0) * 5
ok(ms < 1.0, "varm kostnad %.3f ms/kall (< 1 ms)" % ms)

print("\n6) manglende kanonisk butikk slår gaten AV, ikke alt av")
os.environ["SYMBIOSE_USERS_HOME"] = str(Path(tempfile.mkdtemp()))
cp._INV_CACHE = ()
ok(us.resolve_disabled_skills("morten") == set(),
   "ingen butikk → ingen filtrering (status quo), ikke blackout")
h = us.policy_health()
ok(not h["ok"] and "finnes ikke" in h["reason"], "…men policy_health SIER FRA")
os.environ["SYMBIOSE_USERS_HOME"] = str(HOME)

print("\n7) GATEN SELV — _per_user_disabled, leddet uten dekning")
# Reviewer: kjeden var testet i BITER (get_identity direkte, resolve med et
# literalt brukernavn), men det ØVERSTE leddet — contextvar-lesingen,
# sid-fallbacken, identified-flagget og (a)s fail-lukkede gren — hadde NULL
# dekning. Det er nettopp funksjonen som har båret to feil: den opprinnelige
# no-op-en og fail-open-en. Nå dekkes den.
import importlib, types
sys.modules.setdefault("gateway", types.ModuleType("gateway"))
_sc = types.ModuleType("gateway.session_context")
_ENV = {}
_sc.get_session_env = lambda name, default="": _ENV.get(name, default)
sys.modules["gateway.session_context"] = _sc

import ast
_src = (Path(__file__).resolve().parents[1] / "agent" / "skill_utils.py").read_text()
_ns = {"Set": set, "os": os, "time": time}
for _n in ast.parse(_src).body:
    if isinstance(_n, ast.FunctionDef) and _n.name == "_per_user_disabled":
        exec(compile(ast.Module([_n], []), "skill_utils", "exec"), _ns)
gate = _ns["_per_user_disabled"]

cp._INV_TTL_S, cp._INV_CACHE = 10.0, ()
us.set_capability_policy({"verktoy": "system"}, path=cp.canonical_users_path())
si.set_identity("gate-sid-1", "morten")
si.set_identity("gate-sid-2", "kari")
ALLE = set()
for r in cp.inventory():
    ALLE.update(r["skills"])

def g(label, env, forventet, hvorfor):
    _ENV.clear(); _ENV.update(env)
    got = gate()
    ok(got == forventet, "%-34s %s" % (label, hvorfor))

g("ingen prinsipal", {}, set(), "-> 0 skjult (konsoll/cron: gaten som før)")
g("chat-sesjon = morten (admin)", {"HERMES_SESSION_ID": "gate-sid-1"},
  set(), "-> 0 skjult (eier ser alt)")
g("chat-sesjon = kari (bruker)", {"HERMES_SESSION_ID": "gate-sid-2"},
  ALLE - {"s1", "s2", "s3"}, "-> kun system-kategorien synlig")
g("CHAT_ID-fallback", {"HERMES_SESSION_CHAT_ID": "gate-sid-1"},
  set(), "-> sid kan komme fra chat_id (api_server binder den slik)")
g("ukjent sesjons-id", {"HERMES_SESSION_ID": "finnes-ikke"},
  ALLE - {"s1", "s2", "s3"}, "-> identifisert men ukjent: fail-LUKKET")
g("messaging user_id=morten", {"HERMES_SESSION_USER_ID": "morten"},
  set(), "-> contextvar-stien virker fortsatt")
g("messaging user_id=ukjent", {"HERMES_SESSION_USER_ID": "ingen-slik"},
  ALLE - {"s1", "s2", "s3"}, "-> ukjent bruker: fail-LUKKET")

# (a): resolve KASTER på en identifisert sesjon -> minste sett, ikke største.
_orig = us.resolve_disabled_skills
def _boom(*a, **k):
    raise RuntimeError("simulert korrupt butikk")
us.resolve_disabled_skills = _boom
try:
    _ENV.clear(); _ENV["HERMES_SESSION_ID"] = "gate-sid-1"
    ok(gate() == ALLE - {"s1", "s2", "s3"},
       "identifisert sesjon + oppslaget KASTER  -> system-only, IKKE alt (a)")
    _ENV.clear()
    ok(gate() == set(), "ingen prinsipal + samme feil       -> 0 skjult (legacy urørt)")
finally:
    us.resolve_disabled_skills = _orig

if __name__ == "__main__":
    print("\n" + ("ALLE PASSERTE" if not FAIL else "FEIL: " + "; ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


def test_alle_sjekker_passerte() -> None:
    """Sjekkene over kjører ved import — dette er et skript først og en
    pytest-fil dernest. Uten denne samler pytest null tester og avslutter
    med kode 5, som testkjøreren teller som en feilende fil selv når hver
    eneste sjekk passerte. Assertet er ekte: FAIL fylles av ok().
    """
    assert not FAIL, "; ".join(FAIL)
