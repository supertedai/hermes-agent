"""BL-3404 — selvregistrering + obligatorisk 2FA-innrullering, mot ekte butikk-fil."""
import sys, time, json, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from hermes_cli.dashboard_auth import user_store as us

P = pathlib.Path(tempfile.mkdtemp()) / "users.json"
ok = lambda c, m: print(("  PASS  " if c else "  FAIL  ") + m) or (c or FAIL.append(m))
FAIL = []

print("\n1) bootstrap-admin + søknad inn")
us.create_user(username="morten", password="admin-passord-123", role="admin", path=P)
ok(us.add_pending(username="kari", password="kari-passord-1", display_name="Kari",
                  email="kari@x.no", source_ip="1.2.3.4", path=P), "søknad tatt imot")
pend = us.list_pending(path=P)
ok(len(pend) == 1 and pend[0]["username"] == "kari", "én åpen søknad")
ok("password_hash" not in pend[0], "hash lekker IKKE ut av list_pending")
raw = json.loads(P.read_text())
ok(all("kari-passord-1" not in json.dumps(x) for x in raw["pending"]), "klartekst finnes ikke på disk")

print("\n2) skjemaet er ikke et orakel")
ok(not us.add_pending(username="Kari!", password="x" * 9, path=P), "ugyldig navn avvist")
ok(not us.add_pending(username="morpheus", password="x" * 9, path=P), "reservert navn avvist")
ok(not us.add_pending(username="ola", password="kort", path=P), "for kort passord avvist")
us.add_pending(username="kari", password="kari-passord-2", path=P)
ok(len(us.list_pending(path=P)) == 1, "ny søknad for samme navn dubler ikke køen")
ok(us.list_pending(path=P)[0]["resubmit_count"] == 1, "og den telles som gjenforsøk")

print("\n3) godkjenning → konto med VENTENDE 2FA")
pid = us.list_pending(path=P)[0]["id"]
u = us.approve_pending(pid, approved_by="morten", path=P)
ok(u["username"] == "kari" and u["totp_pending"] and not u["has_totp"], "konto med ventende 2FA")
ok("totp_secret" not in u and "otpauth_uri" not in u, "secreten returneres ALDRI til admin")
ok(us.list_pending(path=P) == [], "søknaden er ute av køen")
closed = us.list_pending(include_closed=True, path=P)
ok(closed[0]["status"] == "approved" and closed[0]["decided_by"] == "morten", "raden består m/ stempel")

print("\n4) innlogging før innrullering gir INGEN sesjon")
r = us.verify_login_ex("kari", "kari-passord-1", path=P)   # FØRSTE gjelder (K3)
ok(r["status"] == "enroll" and r["enroll"]["secret"], "→ enroll, ikke ok")
ok(us.verify_login_ex("kari", "kari-passord-2", path=P)["status"] == "no",
   "det SENERE passordet virker ikke — søknaden kunne ikke kapres")
ok(us.verify_login("kari", "kari-passord-1", path=P) is None,
   "verify_login (dødt API) slipper IKKE inn før innrullering")
ok(us.verify_login_ex("kari", "feil-passord", path=P)["status"] == "no", "feil passord → no")

print("\n5) innrullering krever gyldig kode")
secret = r["enroll"]["secret"]
ok(not us.enroll_totp("kari", "000000", path=P), "feil kode avvist")
ok(us.verify_login_ex("kari", "kari-passord-1", path=P)["status"] == "enroll", "fortsatt ikke innrullert")
good = us._totp_at(secret, time.time())
ok(us.enroll_totp("kari", good, path=P), "gyldig kode innruller")
ok(us.get_public_user("kari", path=P)["has_totp"], "2FA nå PÅ")
ok(not us.enroll_totp("kari", us._totp_at(secret, time.time()), path=P),
   "ruta er død etterpå (ingen ventende secret)")

print("\n6) etter innrullering er 2FA et hardt krav")
ok(us.verify_login_ex("kari", "kari-passord-1", path=P)["status"] == "no", "uten kode → nektet")
ok(us.verify_login_ex("kari", "kari-passord-1", us._totp_at(secret, time.time()),
                      path=P)["status"] == "ok", "med kode → inn")
ok(us.verify_login_ex("kari", "feil", us._totp_at(secret, time.time()),
                      path=P)["status"] == "no", "riktig kode + feil passord → nektet")

print("\n7) avslag")
us.add_pending(username="ola", password="ola-passord-1", path=P)
pid2 = us.list_pending(path=P)[0]["id"]
us.reject_pending(pid2, rejected_by="morten", reason="kjenner ikke", path=P)
ok(us.list_pending(path=P) == [], "ute av køen")
raw = json.loads(P.read_text())
rec = [p for p in raw["pending"] if p["id"] == pid2][0]
ok(rec["status"] == "rejected" and "password_hash" not in rec, "raden består, hashen fjernet")
ok(not any(u["username"] == "ola" for u in raw["users"]), "ingen konto opprettet")

print("\n8) kollisjon + kø-tak")
us.add_pending(username="kari", password="kari-passord-9", path=P)
ok(us.list_pending(path=P)[0]["collision"], "kollisjon flagget for admin")
try:
    us.approve_pending(us.list_pending(path=P)[0]["id"], approved_by="m", path=P)
    ok(False, "godkjenning av kollisjon skal feile")
except ValueError as e:
    ok("finnes allerede" in str(e), "godkjenning av kollisjon feiler tydelig")

print("\n9) den gamle veien er urørt")
u2 = us.create_user(username="uten2fa", password="passord-1234", path=P)
ok(us.verify_login_ex("uten2fa", "passord-1234", path=P)["status"] == "ok",
   "bruker uten 2FA logger inn med tomt kodefelt (forrige turs oppskrift)")
u3 = us.create_user(username="med2fa", password="passord-1234", totp=True, path=P)
ok(u3.get("totp_secret") and u3.get("otpauth_uri"), "totp=True viser secret ÉN gang som før")

# ── Hotfix-regresjoner etter reviewer-BLOCK ────────────────────────────────
print("\n10) K2: lange felt kappes, ikke lagres rått")
us.add_pending(username="lang.bruker", password="p" * 200, display_name="N" * 5000,
               email="e" * 5000 + "@x.no", path=P)
r = us.list_pending(path=P)[0]
ok(len(r["display_name"]) == 80 and len(r["email"]) == 200, "navn/e-post kappet til 80/200")
ok(not us.add_pending(username="for.langt.pw", password="p" * 300, path=P), "passord >256 avvist")

print("\n11) K3: åpen søknad kan ikke kapres")
first = us.list_pending(path=P)[0]
us.add_pending(username="lang.bruker", password="angriper-passord-9", path=P)
now = [p for p in us.list_pending(path=P) if p["username"] == "lang.bruker"][0]
ok(now["id"] == first["id"] and now["created_at"] == first["created_at"], "opprinnelig rad står")
ok(now["resubmit_count"] == 1, "forsøket telles og vises for admin")
u = us.approve_pending(now["id"], approved_by="morten", path=P)
r2 = us.verify_login_ex("lang.bruker", "p" * 200, path=P)
ok(r2["status"] == "enroll", "FØRSTE passord gjelder")
ok(us.verify_login_ex("lang.bruker", "angriper-passord-9", path=P)["status"] == "no",
   "angriperens passord virker IKKE")

print("\n12) verify_login (dødt API) er lukket for innrullerings-tilstanden")
ok(us.verify_login("lang.bruker", "p" * 200, path=P) is None, "nektes til 2FA er innrullert")

print("\n13) last_login lyver ikke om avbrutt innrullering")
ok(us.get_public_user("lang.bruker", path=P)["last_login"] == "", "ikke stemplet av enroll-forsøk")
us.enroll_totp("lang.bruker", us._totp_at(r2["enroll"]["secret"], time.time()), path=P)
us.verify_login_ex("lang.bruker", "p" * 200, us._totp_at(r2["enroll"]["secret"], time.time()), path=P)
ok(us.get_public_user("lang.bruker", path=P)["last_login"] != "", "stemplet ved FULLFØRT innlogging")

print("\n14) (e) godkjenning som feiler ruller søknaden tilbake i køen")
us.add_pending(username="kari", password="kari-passord-x", path=P)   # kari finnes alt
pid3 = [p for p in us.list_pending(path=P) if p["username"] == "kari"][0]["id"]
try:
    us.approve_pending(pid3, approved_by="m", path=P)
except ValueError:
    pass
ok(any(p["id"] == pid3 and p["status"] == "open" for p in us.list_pending(path=P)),
   "raden er tilbake som 'open', ikke tapt i 'approving'")

print("\n" + ("ALLE PASSERTE" if not FAIL else "FEIL: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
