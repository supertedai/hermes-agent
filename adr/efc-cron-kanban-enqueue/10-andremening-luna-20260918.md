# Andremening 2026-09-18 — Hermes/GPT-5.6-luna. IKKE uavhengig.

## Proveniens (målt)

| Felt | Verdi |
|---|---|
| Rute | `hermes chat --query-file … --oneshot -m gpt-5.6-luna --provider openai-api -t none -Q --max-turns 3` |
| Økt | `20260918_101349_18cf1d` (Hermes-sesjon, kilde `kanban`) |
| Modell, som rapportert av runtime | `gpt-5.6-luna` (rad i `session_model_usage`: `billing_provider=openai-api`, `billing_base_url=https://api.openai.com/v1/`) |
| `model_verified` | **nei.** Navnet er det runtime-en førte på fakturaen; ingen attestasjon fra leverandøren er lest. |
| Runde 1 (kastet, avkuttet utskrift) | `20260918_101238_37b4d5`, samme spørsmål |
| Prompt | `luna-9c6375ea-sporsmaal.md` — selve spørsmålet, koden og de alt observerte bevisene; ingen konklusjon fra meg |
| Svar | `luna-9c6375ea-svar.md` (223 linjer) |

**Dette er ikke en uavhengig vurdering i den forstand policyen krever.** Det er
en separat review-runde på en annen modell via samme Hermes-runtime, med
avgrenset kontekst (ingen verktøy, ingen tilgang til repoet, bare beskrivelsen
og koden jeg ga den). Den skal **ikke** omtales som Claude-verifisert eller
modell-uavhengig. Styrken ligger i at den ikke delte mine antakelser — den
leste bare det jeg skrev, og den tok feil på ett punkt der jeg hadde målingen.

## Funn og disposisjon

| # | Alvor | Funn (kort) | Disposisjon |
|---|---|---|---|
| 1 | critical | Nye kort opprettes i `running` uten claim og blir aldri sendt ut | **TILBAKEVIST.** `initial_status` har bare to verdier (`VALID_INITIAL_STATUSES = {"running","blocked"}`), og `running` betyr «den vanlige veien», ikke statusen. Statusen utledes av foreldrene: `ready` når ingen uferdige foreldre. Målt: `{"created": true, "status": "ready"}` fra ekte CLI, og dispatcherens kandidatspørring er `status='ready' AND claim_lock IS NULL`. Luna kunne ikke lese `create_task` og sa det selv. |
| 2 | high | `running`-rader uten gyldig claim blir liggende for alltid | **GYLDIG, MEN UTENFOR.** Gjenvinning finnes og er målt: denne tavla gjenvant sin egen arbeider (`reclaimed`, `stale_lock`) 2026-09-11. Enqueue skal ikke overta lease-gjenvinning. |
| 3 | high | Re-arm etterlater stale claim-metadata → kortet blir uclaimbart | **GYLDIG, RETTET.** Re-arm nuller nå `claim_lock`, `claim_expires` og `worker_pid`; test `test_enqueue_rearm_clears_stale_claim_metadata` (feilet mot gammel kode). |
| 4 | high | list-så-opprett-racet bryter «én rad per nøkkel» | **GYLDIG, ÅPEN RESIDUAL.** Samme egenskap finnes i `create_task` i dag. Krever unik partiell indeks + migrasjon med duplikatreparasjon på levende brett — egen oppgave, ikke denne endringen. |
| 5 | high | nøkkelens omfang/arkiverte rader er underspesifisert | **DELVIS GYLDIG.** Arkivert rad frigjør nøkkelen med vilje (et arkivert kort er historie, ikke aktivt arbeid). Nøkler er produsent-namespacet etter konvensjon (`cron:…`, `efc:…`). Ført i kontrakten over muterbare/immutable felt. |
| 6 | high | samtidige refresher = last-writer-wins | **GYLDIG, ÅPEN RESIDUAL.** Én skriver per nøkkel er regelen; ikke håndhevet i basen. Samme rot som #4. |
| 7 | medium-high | «utelatt = behold» er utrygt som eneste semantikk | **DELVIS IMØTEKOMMET.** Det målte avviket (utelatte flagg nullet kortet) er rettet; utelatt betyr nå «behold», og eierløst kort varsler. `body` kan tømmes eksplisitt med tom streng. Å tømme `assignee` eksplisitt finnes ikke — residual. |
| 8 | high | `review → ready` kan omgå menneskelig review | **GYLDIG INNVENDING, ÅPEN BESLUTNING.** Se «Åpne beslutninger» under. Bevisst valg i `03-decision.md`; ikke endret her. |
| 9 | medium-high | `blocked → ready` kan gi varm løkke mot en uløst avhengighet | **DELVIS IMØTEKOMMET.** `block_kind`/`block_recurrences` beholdes bevisst, så en vedvarende blokk eskalerer; kadensen er ukentlig, ikke per minutt. Åpne beslutning #8/#9 henger sammen. |
| 10 | medium | produsenteide felt oppdateres ikke (workspace/branch/project/created_by) | **GYLDIG, GJORT EKSPLISITT.** Muterbare felt = tittel/body/eier/prioritet; anker og `created_by` er immutable etter oppretting, med grunn i docstringen. |
| 11 | medium | hendelsessporet er ufullstendig (create-veien mangler `enqueued`; ingen fra/til) | **GYLDIG, RETTET.** Create-veien skriver nå `enqueued` med `created: true`, og refresh-hendelsen har `from`/`to`. Test `test_enqueue_records_the_producer_on_the_create_path_too`. |
| 12 | medium | normalisering/feilatferd trenger kontrakt | **DELVIS RETTET.** Tittel strippes nå på begge veier; nøkkelen strippes før oppslag og lagres strippet. Ugyldig `--priority` avvises av argparse (exit 2). Negative/store verdier er tillatt med vilje (rekkefølge-tiebreak). |
| 13 | low/medium | `int(priority)`-validering | **IMØTEKOMMET** av 12. |

## Hva andremeningen faktisk endret

Tre funn ga kode (#3, #11, #12), og de ligger i commit etter `6d5a384c2c`.
Ett funn (#1) ble tilbakevist med kode og måling, og det er det viktigste
resultatet: uten målingen ville jeg ha «rettet» et problem som ikke fantes, og
skrevet `ready` inn i en kodevei som allerede gjør det.

## Åpne beslutninger til mennesket/revieweren

1. **Re-arm av `review` (#8).** I dag flyttes et kort i review tilbake til
   `ready`, og neste arbeider kan gjøre arbeidet på nytt mens en reviewer
   vurderer. Alternativet er å la `review` stå urørt og bare re-arme `done`
   (og `blocked`). Konsekvens målt for den faktiske produsenten: dagens
   `vedlikeholdsrunde.py` regner `blocked` og `review` som ÅPNE kort og gjør
   ingenting med dem — bare `done`/`archived` gir nytt kort. Enqueue er derfor
   et videre løfte enn produsenten bruker i dag.
2. **Re-arm av `blocked` (#9).** Samme avveining: en re-arm gir nytt forsøk,
   men kan også gjenta en blokkering som venter på et menneske. Blokkeringen
   er fortsatt sporbar og eskalerer.
3. **Én eller to produsenter** (tillegg 09, punkt 3): researcher-cronjobben og
   systemd-timeren må ikke bruke ulike nøkler for samme kort.

## Hva jeg IKKE kunne verifisere fra andremeningens side

Unik indeks, migrasjonsvei og samtidighet (#4/#6) er ikke bevist — de er
residualer med forslag, ikke løste. Revieweren bør veie dem mot at produsenten
er én prosess i dag.
