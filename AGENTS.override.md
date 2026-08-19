# AGENTS.override.md — kontrakt for kanban-workere (forken)

Oppstroems egen AGENTS.md er urort; Hermes laster denne foerst.

Denne fila leses av enhver agent som kjører i et arbeidstre av dette repoet,
før `CLAUDE.md`. `CLAUDE.md` er lagets kart og kanonens kondensering — den
gjelder fortsatt. Dette er det **operative** laget: de få tingene en worker
faktisk må gjøre, og som ble målt som udone 2026-08-19.

Kjører du som kanban-worker, står `HERMES_KANBAN_TASK` i miljøet ditt og
arbeidsmappa di er et git-arbeidstre under `.worktrees/t_<hex>`.

## 1. Commit arbeidet ditt. Alltid.

Målt 2026-08-19: åtte arbeidstrær hadde ekte endringer, og **ingen** hadde en
commit. Alt lå staged. Det gjør leveransen til en arbeidskopi ingen har
signert — steg 10-reviewen har da ingen diff å se på, og steg 11–13 har
ingenting å lese tilbake.

Før du melder oppgaven ferdig:

```bash
git add -A
git commit -m "<kort hva>

<hvorfor, hvis det ikke er opplagt>

Aktør: <profilnavn>
Oppgave: <task-id>"
```

Én commit per logisk endring. Aktør og oppgave-ref er ikke pynt — de er
proveniensen kanonens steg 9 krever.

**Push:** kun til din egen `wt/`-gren. `main`, `master` og
`mwp/uosh-automation-01` er beskyttet og vil avvise deg med `GH006`. Det er
tilsiktet. Landing er menneskeord.

## 2. Har du en commit: be om review. Ellers: fullfør.

Regelen er mekanisk, ikke en vurdering:

```bash
git log --oneline mwp/uosh-automation-01..HEAD
```

**Én eller flere commits → `kanban_request_review`.**
**Null commits → `kanban_complete`.**

Det er hele regelen. Du skal ikke vurdere om endringen er «stor nok», om et
dokument «teller som kode», eller om du selv synes den er opplagt riktig. Har
du committet noe, skal en annen se det.

`kanban_request_review` setter kortet i `review`-kolonnen, og dispatcheren
starter en uavhengig instans som ser oppgaven og diffen din og feller dom. Det
er kanonens steg 10, og den eneste gaten mellom arbeidet ditt og menneskeordet.

Målt 2026-08-19: 405 kort sto i `done`, og ikke ett hadde vært innom review.
Da regelen først var formulert som skjønn — «endret du kode eller innhold» —
fullførte en worker et dokument uten review fordi den leste seg selv inn under
unntaket for «rene undersøkelser». Derfor er regelen nå et `git log`-kall.

**Har `kanban_complete` eller `kanban_heartbeat` allerede svart «unknown id or
already terminal/not running»:** da er kortet ferdig registrert. Ikke prøv
igjen, og ikke rapporter det som en feil — det betyr bare at du kaller etter at
tilstanden er satt.

**Er du revieweren** og dommen er godkjent: push grenen og åpne pull request
før du fullfører kortet.

```bash
git push -u origin "$(git branch --show-current)"
gh pr create --base main --title "<hva>" --body "<hvorfor + oppgave-ref + dommen din>"
```

Uten dette blir arbeidet liggende i et arbeidstre på serveren, usynlig på
GitHub. Målt 2026-08-19: sytten `wt/`-grener lokalt, null pushet — alt som var
bygget den dagen var utilgjengelig for menneskene som skulle lande det.

PR-en er leveransen. Steg 11–13 — pre-landing-kontroll, runtime-smoke og
tilbakelesing etter merge — er **menneskets**, og det er F5-grensen i ADR-005.
Den er der med vilje. Ikke merge selv, og ikke be om å få lov.

## 3. `result` er obligatorisk. Alltid.

**Et kort som fullføres uten `result` har ikke levert noe.**

`kanban_complete` tar en `summary`. Den skal alltid fylles, uansett hvor lite
kortet gjorde. Dette er ikke en høflighetsformulering — for kort som ikke
etterlater en diff er `result` det **eneste** sporet som finnes. Uten den ser
kortet ferdig ut og har produsert null lesbart.

Målt 2026-08-19: 43 kort fullført samme dag, **ett** hadde `result`. To
analysekort — «Definer ledger-modell», «Lag skriveallowlist og preflight-plan»
— fullførte helt korrekt uten commit, og etterlot seg dermed ingenting i det
hele tatt.

Hva `result` skal si, i denne rekkefølgen:

1. **Hva du konkluderte** — svaret, ikke prosessen. Én til tre setninger.
2. **Hva du bygde på** — filer, målinger, kommandoer. Navngi dem.
3. **Hva du ikke fikk avklart** — og hvorfor. Fravær av data er ikke et
   positivt funn.

Er kortet rent analyse og konklusjonen er lengre enn noen setninger: skriv den
til en fil i arbeidsområdet, commit den, og la `result` peke på den. Da faller
kortet inn under punkt 2 og skal til review.

### Artefakter i scratch-arbeidsområder

`scratch` slettes ved fullføring. Skrev du en fil og ikke deklarerte den, er
den borte — målt: fjorten kort fullført, null vedlegg. Oppgi derfor artefaktene
til `kanban_complete` med absolutte stier inne i arbeidsområdet.

I et `worktree` er commiten selv artefaktet. `result` skal likevel fylles.

## 4. Meld manglende evne som manglende evne

Finner du ikke en sti, mangler du en tilgang, eller er kilden ikke montert i
runtime — **blokker oppgaven med `capability` og si hva som mangler.** Ikke
gjett, ikke bygg noe plausibelt i nærheten.

Dette gjøres allerede godt: sju kort blokkerte 2026-08-19 med presis tekst om
hvilken sti som manglet, og den diagnosen var det som gjorde dem fiksbare.
Motsatt: ett kort rapporterte «38 tester passerte» om filer i en sandkasse som
ble revet — påstanden var uetterrettelig fordi ingenting overlevde.

Fravær av data er ikke et positivt funn.

## 5. Hvor ting hører hjemme

| Du vil endre | Repo | Merknad |
|---|---|---|
| `hermes-opus/`, `hermes-skills/`, `hermes-faber/`, `adr/`, `docs/` | dette repoet | arbeidstreet ditt |
| `faber_worker.py`, `faber_governed.py`, `faber_status.py` … | `supertedai/faber-ops` | eget repo |
| `gateway/`, `tools/`, `hermes_cli/`, `agent/`, `apps/desktop/` | `supertedai/hermes-agent` (fork) | vendored plattformkode |

Ligger målet ditt utenfor arbeidstreet ditt: **blokker med `capability`.** Ikke
speil filen inn hit for å komme videre — to sannhetskilder for samme kode er
nøyaktig driften ADR-002 ble skrevet mot.

`~/.hermes/hermes-agent` er vendored og blir `git checkout`-et 04:30 hver natt.
En endring der overlever ikke natten.

## 6. Les kanonen

`CLAUDE.md` og `MAAL.md` ligger i arbeidstreet ditt. Gjeldende ADR-er ligger i
`adr/`. Berører oppgaven din en beslutning som allerede er tatt, gjelder den —
også når oppgaveteksten ikke nevner den.
