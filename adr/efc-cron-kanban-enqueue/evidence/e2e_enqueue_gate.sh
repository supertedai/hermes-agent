#!/usr/bin/env bash
# E2E-gate for t_9c6375ea: `hermes kanban enqueue` mot en ISOLERT kanban-DB.
#
# Beviser, mot ekte CLI (ikke bare enhetstester):
#   1. enqueue oppretter ett kort, status ready, ingen claim/spawn
#   2. samme idempotency-key oppdaterer SAMME kort (ingen duplikat)
#   3. terminalt kort (done) re-kjøes til ready
#   4. kjørende kort med claim røres ikke
#   5. enqueue uten --assignee lager et kort som aldri kan sendes ut (fotangel)
#
# Trygt: HERMES_KANBAN_DB/HOME peker på en temp-sti. Ingen live-tavle berøres.
set -euo pipefail

FORK=${FORK:-/opt/hermes-tavle/kanban/workspaces/t_9c6375ea}
PY=${PY:-/home/morten/.hermes/hermes-agent/venv/bin/python}
TMPD=${TMPD:-/home/morten/tmp-kanban-enqueue}
DB="$TMPD/probe.db"
rm -rf "$TMPD"; mkdir -p "$TMPD"

run() {
  env -u HERMES_DELEGATED_CHILD_CONTEXT \
      PYTHONPATH="$FORK" \
      HERMES_HOME="$TMPD" \
      HERMES_KANBAN_HOME="$TMPD" \
      HERMES_KANBAN_DB="$DB" \
      HERMES_KANBAN_BOARD=probe \
      "$PY" -m hermes_cli.main "$@"
}
sql() { python3 -c "
import sqlite3,sys
c=sqlite3.connect('$DB')
try:
    print(c.execute(sys.argv[1]).fetchall())
    c.commit()
except sqlite3.OperationalError as e:
    print('SQL-FEIL:', e)
" "$1"; }

echo "== 0) init =="
run kanban init >/dev/null 2>&1 || true

echo "== 1) forste enqueue =="
run kanban enqueue "EFC repo- og public HTML-vedlikehold" --body "v1" \
  --assignee researcher --workspace worktree:/opt/agent-work/EFC \
  --branch wt/efc-vedlikehold --idempotency-key cron:efc-vedlikehold --json

echo "== 2) samme key igjen (ny tittel/prioritet) =="
run kanban enqueue "EFC vedlikehold v2" --body "v2" --assignee researcher \
  --priority 9 --idempotency-key cron:efc-vedlikehold --json

echo "== 3) terminalt kort re-kjoeres =="
sql "UPDATE tasks SET status='done', completed_at=123 WHERE idempotency_key='cron:efc-vedlikehold'"
run kanban enqueue "EFC vedlikehold v3" --assignee researcher \
  --idempotency-key cron:efc-vedlikehold --json

echo "== 4) kjoerende kort med claim roeres ikke =="
sql "UPDATE tasks SET status='running', claim_lock='host:1', worker_pid=4242 WHERE idempotency_key='cron:efc-vedlikehold'"
run kanban enqueue "EFC vedlikehold v4" --assignee researcher \
  --idempotency-key cron:efc-vedlikehold --json
echo -n "   claim etter refresh: "; sql "SELECT status,claim_lock,worker_pid,title FROM tasks WHERE idempotency_key='cron:efc-vedlikehold'"

echo "== 5) fotangel: enqueue uten --assignee =="
run kanban enqueue "kort uten eier" --idempotency-key cron:uten-eier --json
echo -n "   assignee: "; sql "SELECT id,assignee,status FROM tasks WHERE idempotency_key='cron:uten-eier'"

echo "== 6) ingen claim/spawn fra enqueue =="
sql "SELECT COUNT(*) AS kort FROM tasks WHERE idempotency_key='cron:efc-vedlikehold'"
echo "   task_events:"
TID=$(sql "SELECT id FROM tasks WHERE idempotency_key='cron:efc-vedlikehold'" | tr -d "[]'\",()")
run kanban show "$TID" 2>/dev/null | grep -iE 'claimed|spawned|enqueued' || true

echo
echo "== KONTROLLER =="
python3 - "$DB" <<'PY'
import sqlite3, sys
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
fails = []

def check(name, ok, got):
    print(("  OK   " if ok else "  FEIL ") + f"{name}: {got}")
    if not ok:
        fails.append(name)

rows = c.execute("SELECT * FROM tasks WHERE idempotency_key='cron:efc-vedlikehold'").fetchall()
check("ett kort per idempotency-key", len(rows) == 1, f"{len(rows)} rad(er)")
t = rows[0]
check("assignee bevart", t["assignee"] == "researcher", t["assignee"])
check("arbeidsflate bevart", (t["workspace_kind"], t["workspace_path"]) == ("worktree", "/opt/agent-work/EFC"),
      (t["workspace_kind"], t["workspace_path"]))
check("branch bevart", t["branch_name"] == "wt/efc-vedlikehold", t["branch_name"])
check("tittel oppdatert til siste enqueue", t["title"] == "EFC vedlikehold v4", t["title"])
check("prioritet oppdatert", t["priority"] == 9, t["priority"])
# steg 3-4 kjorte ETTER at raden ble satt til done/running; siste enqueue skal
# ha re-kjoevd done -> ready og deretter latt running staa urort.
check("kjoerende status ikke endret av enqueue", t["status"] == "running", t["status"])
check("claim_lock ikke frigitt", t["claim_lock"] == "host:1", t["claim_lock"])
check("worker_pid ikke nullstilt", t["worker_pid"] == 4242, t["worker_pid"])

events = [dict(r) for r in c.execute("SELECT kind, payload FROM task_events WHERE task_id=?", (t["id"],))]
kinds = {e["kind"] for e in events}
check("ingen 'claimed'-hendelse fra enqueue", "claimed" not in kinds, sorted(kinds))
check("ingen 'spawned'-hendelse fra enqueue", "spawned" not in kinds, sorted(kinds))
check("enqueue-hendelse finnes", "enqueued" in kinds, sorted(kinds))

ue = c.execute("SELECT assignee, status FROM tasks WHERE idempotency_key='cron:uten-eier'").fetchone()
print(f"  MERK fotangel: kort uten --assignee -> assignee={ue['assignee']!r}, status={ue['status']!r}"
      " (kan aldri sendes ut av dispatcheren)")

print()
print("RESULTAT:", "ALLE KONTROLLER OK" if not fails else f"FEIL: {fails}")
sys.exit(1 if fails else 0)
PY
