"""BL-3404 rev2 — selvregistrering med 2FA I SKJEMAET (Morten: «hvor er 2fa???»).

rev1 satte opp 2FA ved søkerens første innlogging. Nå skjer det i
registreringsskjemaet: gaten verifiserer en ekte kode mot nøkkelen FØR
søknaden sendes, så alt som når admin-flaten er ferdig 2FA-sikret — og hele
innrullerings-steget (og token-typen som ga K1) er borte.
"""
import sys, time, json, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from hermes_cli.dashboard_auth import user_store as us

P = pathlib.Path(tempfile.mkdtemp()) / "users.json"
FAIL = []
ok = lambda c, m: print(("  PASS  " if c else "  FAIL  ") + m) or (c or FAIL.append(m))
SEC = us.generate_totp_secret
now = lambda s: us._totp_at(s, time.time())

print("\n1) bootstrap + søknad med 2FA-nøkkel")
us.create_user(username="morten", password="admin-passord-123", role="admin", path=P)
s_kari = SEC()
ok(us.add_pending(username="kari", password="kari-passord-1", display_name="Kari",
                  email="kari@x.no", source_ip="1.2.3.4", totp_secret=s_kari, path=P),
   "søknad med nøkkel tatt imot")
pend = us.list_pending(path=P)
ok(len(pend) == 1 and pend[0]["username"] == "kari", "én åpen søknad")
ok("password_hash" not in pend[0] and "totp_secret" not in pend[0],
   "verken hash eller 2FA-nøkkel lekker ut av list_pending")
raw = json.loads(P.read_text())
ok(all("kari-passord-1" not in json.dumps(x) for x in raw["pending"]),
   "klartekst-passord finnes ikke på disk")

print("\n2) en søknad UTEN gyldig 2FA-nøkkel er ikke en søknad")
ok(not us.add_pending(username="uten2fa", password="passord-1234", path=P),
   "manglende nøkkel avvist")
ok(not us.add_pending(username="rar2fa", password="passord-1234",
                      totp_secret="ikke-base32!", path=P), "malformt nøkkelformat avvist")

print("\n3) skjemaet er ikke et orakel")
ok(not us.add_pending(username="Kari!", password="x" * 9, totp_secret=SEC(), path=P),
   "ugyldig navn avvist")
ok(not us.add_pending(username="morpheus", password="x" * 9, totp_secret=SEC(), path=P),
   "reservert navn avvist")
ok(not us.add_pending(username="ola", password="kort", totp_secret=SEC(), path=P),
   "for kort passord avvist")

print("\n4) K3: en åpen søknad kan ikke kapres — men kan repareres av Morten")
first = us.list_pending(path=P)[0]
s_ang = SEC()
us.add_pending(username="kari", password="angriper-passord", totp_secret=s_ang, path=P)
n = us.list_pending(path=P)[0]
ok(len(us.list_pending(path=P)) == 1 and n["id"] == first["id"], "dubler ikke, erstatter ikke")
ok(n["resubmit_count"] == 1 and len(n["attempts"]) == 2, "begge innsendinger BEVART")
ok(all("password_hash" not in a and "totp_secret" not in a for a in n["attempts"]),
   "ingen hemmeligheter i forsøks-visningen")

print("\n5) godkjenning → konto som ER 2FA-sikret, uten mellomtilstand")
u = us.approve_pending(n["id"], approved_by="morten", path=P)   # attempt=0 = standard
ok(u["username"] == "kari" and u["has_totp"], "2FA på med én gang")
ok("totp_secret" not in u and "otpauth_uri" not in u, "nøkkelen returneres ALDRI til admin")
ok("totp_pending" not in u, "ingen ventende-tilstand finnes lenger")
raw = json.loads(P.read_text())
rec = [p for p in raw["pending"] if p["id"] == n["id"]][0]
ok(rec["status"] == "approved" and "totp_secret" not in rec and "password_hash" not in rec,
   "søknaden beholder stempel, men ingen kopi av hemmelighetene")

print("\n6) 2FA er et hardt krav fra første innlogging")
ok(us.verify_login_ex("kari", "kari-passord-1", path=P)["status"] == "no", "uten kode → nektet")
ok(us.verify_login_ex("kari", "kari-passord-1", now(s_kari), path=P)["status"] == "ok",
   "med kode → inn (FØRSTE passord gjelder, K3)")
ok(us.verify_login_ex("kari", "angriper-passord", now(s_kari), path=P)["status"] == "no",
   "angriperens passord virker ikke")
ok(us.verify_login_ex("kari", "kari-passord-1", "000000", path=P)["status"] == "no",
   "feil kode → nektet")
ok(us.verify_login("kari", "kari-passord-1", now(s_kari), path=P) is not None,
   "verify_login enig med verify_login_ex")

print("\n7) last_login lyver ikke")
us.verify_login_ex("kari", "kari-passord-1", path=P)               # mislykket
ll = us.get_public_user("kari", path=P)["last_login"]
us.verify_login_ex("kari", "kari-passord-1", now(s_kari), path=P)  # vellykket
ok(us.get_public_user("kari", path=P)["last_login"] >= ll, "stemples kun ved fullført innlogging")

print("\n8) avslag etterlater ingenting brukbart")
us.add_pending(username="ola", password="ola-passord-1", totp_secret=SEC(), path=P)
pid = [p for p in us.list_pending(path=P) if p["username"] == "ola"][0]["id"]
us.reject_pending(pid, rejected_by="morten", reason="kjenner ikke", path=P)
raw = json.loads(P.read_text())
rec = [p for p in raw["pending"] if p["id"] == pid][0]
ok(rec["status"] == "rejected", "raden består med stempel")
ok("password_hash" not in rec and "totp_secret" not in rec, "hash OG nøkkel fjernet")
ok(not any(x["username"] == "ola" for x in raw["users"]), "ingen konto opprettet")

print("\n9) M3: tidligere avgjørelser følger en ny søknad")
us.add_pending(username="ola", password="ola-passord-2", totp_secret=SEC(), path=P)
row = [p for p in us.list_pending(path=P) if p["username"] == "ola"][0]
ok(bool(row["prior_decisions"]) and row["prior_decisions"][-1]["status"] == "rejected",
   "Morten ser sin egen forrige avgjørelse")

print("\n10) K2: lange felt kappes")
us.add_pending(username="lang.bruker", password="p" * 200, display_name="N" * 5000,
               email="e" * 5000 + "@x.no", totp_secret=SEC(), path=P)
r = [p for p in us.list_pending(path=P) if p["username"] == "lang.bruker"][0]
ok(len(r["display_name"]) == 80 and len(r["email"]) == 200, "navn/e-post kappet til 80/200")
ok(not us.add_pending(username="langt.pw", password="p" * 300, totp_secret=SEC(), path=P),
   "passord >256 avvist")

print("\n11) (e) godkjenning som feiler ruller søknaden tilbake i køen")
us.add_pending(username="kari", password="kari-passord-x", totp_secret=SEC(), path=P)
pid2 = [p for p in us.list_pending(path=P) if p["username"] == "kari"][0]["id"]
try:
    us.approve_pending(pid2, approved_by="m", path=P); ok(False, "skal feile på unikhet")
except ValueError as e:
    ok("finnes allerede" in str(e), "godkjenning av kollisjon feiler tydelig")
ok(any(p["id"] == pid2 and p["status"] == "open" for p in us.list_pending(path=P)),
   "raden er tilbake som 'open', ikke tapt i 'approving'")

print("\n12) mistet telefon: Morten kan bevisst velge en senere innsending")
s_a, s_b = SEC(), SEC()
us.add_pending(username="per", password="per-forste-1", totp_secret=s_a, source_ip="1.1.1.1", path=P)
us.add_pending(username="per", password="per-andre-22", totp_secret=s_b, source_ip="2.2.2.2", path=P)
row = [p for p in us.list_pending(path=P) if p["username"] == "per"][0]
ok(len(row["attempts"]) == 2 and row["attempts"][1]["ip"] == "2.2.2.2", "begge synlige m/ opphav")
try:
    us.approve_pending(row["id"], approved_by="m", attempt=9, path=P); ok(False, "skal feile")
except ValueError as e:
    ok("ukjent innsending" in str(e), "ugyldig valg avvises")
    ok(any(p["id"] == row["id"] for p in us.list_pending(path=P)), "og raden blir liggende åpen")
us.approve_pending(row["id"], approved_by="morten", attempt=1, path=P)
ok(us.verify_login_ex("per", "per-andre-22", now(s_b), path=P)["status"] == "ok",
   "valgt innsending ble kontoen")
ok(us.verify_login_ex("per", "per-forste-1", now(s_a), path=P)["status"] == "no",
   "den forkastede innsendingen virker IKKE")
raw = json.loads(P.read_text())
rec = [x for x in raw["pending"] if x["id"] == row["id"]][0]
ok(rec["decided_attempt"] == 1, "hvilken innsending som ble valgt er stemplet")
ok(all("password_hash" not in a and "totp_secret" not in a for a in rec["attempts"]),
   "ALLE forsøk strippet for hemmeligheter etter avgjørelse")

print("\n13) admin-veiene er urørt")
u2 = us.create_user(username="admin.laget", password="passord-1234", totp=True, path=P)
ok(bool(u2.get("totp_secret") and u2.get("otpauth_uri")), "totp=True viser nøkkel ÉN gang som før")
us.create_user(username="uten.2fa", password="passord-1234", path=P)
ok(us.verify_login_ex("uten.2fa", "passord-1234", path=P)["status"] == "ok",
   "admin kan fortsatt lage bruker uten 2FA")
us.set_totp("admin.laget", None, path=P)
ok(not us.get_public_user("admin.laget", path=P)["has_totp"], "2FA av virker")

print("\n14) F6: krasj etter vellykket opprettelse etterlater ingen levende nokkel")
s_f6 = SEC()
us.add_pending(username="krasj.test", password="krasj-passord-1", totp_secret=s_f6, path=P)
pid6 = [p for p in us.list_pending(path=P) if p["username"] == "krasj.test"][0]["id"]
# Simuler: create_user lyktes, men prosessen dode for stemplingen.
raw = json.loads(P.read_text())
row = [x for x in raw["pending"] if x["id"] == pid6][0]
us.create_user(username="krasj.test", password_hash=row["attempts"][0]["password_hash"],
               totp_secret=s_f6, path=P)
raw = json.loads(P.read_text())
for x in raw["pending"]:
    if x["id"] == pid6:
        x["status"] = "approving"; x["approving_since"] = time.time() - 9999
P.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
ok(any(p["id"] == pid6 for p in us.list_pending(path=P)), "raden dukker opp igjen som apen")
try:
    us.approve_pending(pid6, approved_by="morten", path=P)
except ValueError:
    pass
raw = json.loads(P.read_text())
rec = [x for x in raw["pending"] if x["id"] == pid6][0]
ok(rec["status"] == "approved", "gjenkjent som VAR fullfort, ikke rullet tilbake i evighet")
ok(all("totp_secret" not in a and "password_hash" not in a for a in rec["attempts"]),
   "det levende TOTP-froet er strippet")

print("\n15) F7: en apen soknad utloper og strippes")
s_g = SEC()
us.add_pending(username="gammel.sok", password="gammel-passord", totp_secret=s_g, path=P)
raw = json.loads(P.read_text())
for x in raw["pending"]:
    if x["username"] == "gammel.sok":
        x["created_epoch"] = time.time() - us.PENDING_TTL_S - 60
P.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
ok(not any(p["username"] == "gammel.sok" for p in us.list_pending(path=P)), "ute av koen")
raw = json.loads(P.read_text())
rec = [x for x in raw["pending"] if x["username"] == "gammel.sok"][0]
ok(rec["status"] == "expired" and "auto" in rec["decided_by"], "auto-avslatt m/ stempel")
ok(all("totp_secret" not in a and "password_hash" not in a for a in rec["attempts"]),
   "hash OG nokkel strippet ved utlop")
ok(us.add_pending(username="gammel.sok", password="ny-passord-123", totp_secret=SEC(), path=P),
   "og navnet er fritt for en ny soknad")

print("\n" + ("ALLE PASSERTE" if not FAIL else "FEIL: " + "; ".join(FAIL)))
if FAIL:
    raise AssertionError("; ".join(FAIL))
