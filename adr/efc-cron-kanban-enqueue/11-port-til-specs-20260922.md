# Tillegg 2026-09-22 — porten til `_SPECS`-treet (kort t_16db1a56)

Dette tillegget er ført inn etter `10-andremening-luna-20260918.md` og erstatter
ingenting. Det dokumenterer hvorfor branchen er flyttet fra `main` til
`upstream-main`, hva porten består av, hva som ble tilpasset underveis, og hva
som fortsatt er menneskegate.

## 1. Målt gap: PR #13s base har ikke parser-treet runtimeen bruker

* Forslaget i PR #13 la `enqueue` i den **imperative** parseren:
  `hermes_cli/kanban.py::build_parser` → `sub.add_parser("enqueue", …)`.
* Den **utrullede** runtimeen (`~/.hermes/hermes-agent`) bygger `hermes kanban`-treet
  fra `hermes_cli/kanban_parser.py::_SPECS` siden `5cc3651b3b1` (2026-09-02, «extract
  data-driven argparse tree to kanban_parser…»), og `hermes_cli/kanban.py` har
  verken `build_parser` eller `add_parser` der.
* PR #13s base (`056547bd98`, 2026-09-08) har `5cc3651b3b1` **ikke** som ane.
  Målt: `git merge-base --is-ancestor 5cc3651b3b1 056547bd98` → nei.
  Verbet finnes derfor ikke i treet som faktisk kjører: 45 verb i `_SPECS`, uten
  `enqueue`.

Konsekvensen var målt i produsentkontraktens egen kjøring: linjen for
`efc-vedlikehold` sto `VENTER` fordi inngangen ikke fantes i runtimeen. Å lande
PR #13 er altså ikke å rulle ut `enqueue`.

## 2. Porten: samme semantikk, riktig tre

Branchen er rebaset til `upstream-main` (samme base som PR #16–#19 i forken) og
består av:

| Fil | Endring |
|---|---|
| `hermes_cli/kanban_parser.py` | `_cmd("enqueue", […])` i `_SPECS`, rett etter `create` |
| `hermes_cli/kanban.py` | `"enqueue": _cmd_enqueue` i `_HANDLERS`, og `_cmd_enqueue` |
| `hermes_cli/kanban_db.py` | `enqueue_task(...)` — **uendret** fra PR #13 |
| `tests/hermes_cli/test_kanban_enqueue.py` | PR #13s 9 tester + én port-test |
| `adr/efc-cron-kanban-enqueue/**` | designrecordet, portet uendret |

Re-arm-semantikken er ikke rørt: `done`/`blocked`/`review` → `ready`, eller
`todo` når et foreldre ikke er ferdig; `claim_lock`/`claim_expires`/`worker_pid`
nullstilles; `consecutive_failures`/`last_failure_error` nullstilles mens
`block_kind`/`block_recurrences` beholdes; `enqueued`-hendelse med
`created: true|false`; utelatte flagg betyr «behold», ikke null.

## 3. Det som måtte tilpasses i porten, og hvorfor

Bare det som følger av at treet er et annet — ingen atferdsendring:

* `kbc.connect_closing()` i stedet for `kb.connect_closing()`: den gamle stien er
  en plugin-compat-alias som CI-en ikke tillater intern bruk av.
* `kbd._default_spawn(task, workspace)` i stedet for `kb._default_spawn`: funksjonen
  bor i `kanban_db_dispatch` i det nye treet.
* `workspace_kind=ws_kind or "scratch"`: `_parse_workspace_flag` svarer
  `Optional[str]`; parserens default er `scratch`, så fravær betyr det samme som før.
* `--json` skriver **én linje** (`json.dumps`) og ikke `_print_json` (indent=2):
  produsenter og e2e-gaten leser svaret linjevis, og stderr-varselet for et kort
  uten eier skal ikke gjøre svaret uparsbart. Dette er PR #13s kontrakt.
* `_cmd_enqueue` svarer med `_err(...)` (husets sti) i stedet for `print(..., file=sys.stderr)`
  for de to brukerfeilene, og leser statusen fra `payload`-en i stedet for fra
  `task.status` (som er `Optional`).

## 4. Verifikasjon (kjørt, ikke påstått)

* **Enhetstester:** `10 passed` (`tests/hermes_cli/test_kanban_enqueue.py`).
* **Implementasjonen, ikke bare treet:** PR #13s enhetstester går gjennom
  `run_slash` → `kanban_parser.build_parser` → `_SPECS`. Den nye port-testen
  `test_enqueue_verb_lives_in_the_data_driven_parser_tree` leser `_SPECS` selv og
  parser en `enqueue`-argv, så en `_HANDLERS`-oppføring uten parser-post felles.
* **Negativ kontroll (mutasjoner, kjørt og reversert):** verbet tatt ut av
  `_SPECS` → 9 av 10 tester feiler; `"enqueue": _cmd_enqueue` tatt ut av
  `_HANDLERS` → 9 av 10 feiler. Etter reversering er filene byte-identiske
  (`md5sum`) og suiten er grønn igjen.
* **Regresjon:** kanban-subsettet (72 testfiler) i endret tre mot uendret
  `origin/upstream-main`; feilsettet er sammenlignet, se `subset_summary` i
  kortets tråd.
* **E2E mot ekte CLI:** `evidence/e2e_enqueue_gate.sh` — ALLE KONTROLLER OK, mot
  `_SPECS`-treet (gaten skriver selv hvilket parser-tre den kjørte mot).
* **Produsentkontrakten:** med port-treet spilt inn som `--runtime` melder linjen
  for `efc-vedlikehold` **OK**: «inngangen «hermes kanban enqueue» finnes i
  runtimeen (46 verb, hermes_cli/kanban_parser.py)». Mot den faktiske utrullede
  runtimeen står den fortsatt på `VENTER` — se punkt 5.

## 5. Menneskgatene, uendret

* **Utrulling.** Denne branchen er et forslag. Verbet svarer først i runtimeen når
  endringen er landet og rullet ut; før det er `VENTER`-linjen den korrekte
  målingen. Produsentkontrakten mot den utrullede runtimeen er derfor `VENTER`
  fortsatt.
* **Oppstrøms.** Runtimeen følger `NousResearch/hermes-agent`. Porten må
  videreføres oppstrøms (eller bevisst holdes som fork-patch) for å nå koden som
  kjører. `upstream-main`-basen gjør den arvelig for forken; oppstrømsveien er
  menneskeord.
* **Eierskapet (cron vs systemd-timer)** for EFC-vedlikeholdskortet er som før en
  menneskebeslutning.

## 6. Funn utenfor porten: to ankere i produsentkontraktens definisjon er døde

Målt under kjøringen, og rapportert, ikke rettet her (definisjonen ligger i
Hetzner-repoet, ikke i denne branchen):

* `unblock-tar-bare-blocked` peker på `hermes_cli/kanban_db.py:3535`; ankeret står
  nå på linje 3644 i den utrullede runtimeen (±60-vinduet er passert) → `FRAVÆR`.
* `inngang` (merket `tre: fork`) anker på
  `'Idempotently create or refresh one automation-owned task'` i
  `hermes_cli/kanban.py`. Etter porten står den strengen i
  `hermes_cli/kanban_parser.py` (hjelpeteksten), og `kanban.py` bærer
  docstringen `_cmd_enqueue`. Kildehenvisningen må måles på nytt.

`FRAVÆR` er en hardere tilstand enn `VENTER` («kunne ikke måle» skal ikke se ut som
et svar), så de to bør rettes i definisjonen — som eget arbeid, i riktig repo.

Aktør: default · Oppgave: t_16db1a56
