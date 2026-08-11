# ADR — Second opinion i Fabers 13-stegs autocoder-kjede

- **BL:** BL-4055
- **Dato:** 2026-08-11
- **Status:** Vedtatt. **Del 1 av 2 landet** — politikk, transport, GUI-rute
  og tester. **Håndhevelsen i kjeden gjenstår** (del 2), se «Status per del».
- **Kode (del 1, landet):** `agent/second_opinion.py`,
  `agent/second_opinion_client.py`, `tests/test_second_opinion.py`,
  GUI-rute `POST /api/faber/second-opinion` (`hermes_cli/web_server.py`,
  `hermes_cli/web_models.py`)
- **Kode (del 2, gjenstår):** wiring i `agent/code_workflow.py`
  (`GovernedCodeRunner.run`) + `ReviewEvidence.confidence`

### Status per del — les denne før du siterer noe under

| Del | Innhold | Status |
|-----|---------|--------|
| 1 | Utløser, uenighetspolitikk, uavhengighetssjekk, fail-closed, nøkkelfil, GUI-rute, 89 tester | **landet** |
| 2 | `GovernedCodeRunner.run` kaller gaten; `ReviewEvidence.confidence` bærer selvrapporten; begge stemmer skrives i `GovernedRunResult`-evidensen | **gjenstår** — `agent/code_workflow.py` holdes av en parallell sesjon (BL-4052) |

**Inntil del 2 er landet, HÅNDHEVER ingenting denne gaten.** Politikken finnes,
og GUI-ruta kan kjøre den — men `grep second_opinion agent/code_workflow.py` gir
null treff, og en gate uten kallested stopper ingenting. Det er nøyaktig
defektklassen `ScopeBudget` og `BlGate` hadde før BL-4029, og den skal stå
skrevet her i klartekst i stedet for å bli oppdaget av neste leser.

Denne oppføringen står her fordi reviewer felte førsteutkastet av ADR-en på
akkurat dette: den erklærte «Vedtatt og implementert» og siterte wiring,
`ReviewEvidence.confidence` og evidens-skriving som ikke fantes i koden — altså
«evidence asserted rather than measured», i ADR-en for den gaten som
politiserer nettopp det.

---

## Kontekst — det MAALTE utgangspunktet

Målt 2026-08-11 før denne endringen: **null treff** på `second_opinion`,
`dissent` eller `adversarial` i `agent/`. De åtte grep-treffene i repoet var
`optional-skills/dogfood/adversarial-ux-test` (en UX-testskill) og
`creative-ideation/premortem-and-inversion`. Kjeden hadde ingen andre-mening
i det hele tatt.

`GovernedCodeRunner.run` kjører i dag:

```
preflight → bl_gate → owner_gate → design_gate → tests → scope_budget
          → reviewer → landing_scope → DoD → landing
```

Steg 10 (`reviewer`) er én vurderer. Den gir PASS / BLOCK / NEEDS_REVIEW via
`ReviewVerdict`, og en PASS derfra var endelig. Modellen som gir den PASS-en
er den samme familien som produserte endringen — Faber vurderer Fabers arbeid.

## Beslutning 1 — vurdereren er Claude Opus via Anthropic API

Mortens direktiv, gjengitt fordi det er hele premisset:

> Second opinion skal være Claude Opus via API, kalt fra Hermes GUI. Ikke
> cortex-modellen på `.13:1234` — poenget er en **uavhengig** vurderer, og en
> modell som spør seg selv er ikke en andre mening.

Dette er kodet som en **mekanisk sjekk**, ikke en konvensjon
(`second_opinion.assert_independent` + base-URL-sjekken i klienten):

- `provenance` må være `anthropic.api`.
- Modellnavnet i svaret må begynne på `claude-opus`.
- Er `ANTHROPIC_BASE_URL` satt til noe som ikke er `api.anthropic.com`,
  avvises kallet før det gjøres.

Et svar som ikke består uavhengighetssjekken avvises **selv når det er en
CONCUR**. Grunnen til at dette er mekanisk og ikke dokumentert-som-regel er
den samme som `ScopeBudget` demonstrerte før BL-4029: en regel ingen spør om,
er ikke en regel.

## Beslutning 2 — utløseren er målbar, og to av fem er selvrapport-uavhengige

Designkravet som avgjør om andre-meningen er ekte:

> **En second opinion som bare påkalles når man allerede er i tvil, kalles
> aldri når man tar feil med selvtillit.**

Derfor er utløseren ikke «ved behov», og heller ikke bare «lav confidence».
Et utløsersett som utelukkende leser reviewerens egen selvrapport, er et sett
reviewer selv kan lukke ved å være sikker.

`SecondOpinionTrigger` fyrer på **hvilken som helst** av disse — evaluert bare
der kjeden ellers ville sluppet endringen gjennom, altså på en reviewer-PASS:

| # | Utløser | Terskel | Leser selvrapporten? |
|---|---------|---------|----------------------|
| T1 | `confidence_below_0.8` | `confidence < 0.80` | ja |
| T2 | `confidence_unmeasured` | feltet mangler / er ikke et tall / er NaN | ja (fravær av) |
| T3 | `blast_radius_files` / `blast_radius_lines` | `≥ 5 filer` eller `≥ 200 linjer` | **nei** |
| T4 | `blast_radius_unmeasured` | build rapporterte ikke tallene | **nei** |
| T5 | `governance_surface` | landingssettet rører selve vaktmaskineriet | **nei** |

**T3 og T5 er de som gjør den ekte.** De fyrer på en PASS med confidence 0.99.
Det finnes en test som er skrevet nettopp for å holde den egenskapen fast
(`test_blast_radius_triggers_despite_maximum_confidence`) — hvis noen senere
gjør utløseren rent confidence-basert, faller den testen.

Tersklene i T3 er bevisst rundt **halvparten** av `ScopeBudget`s grenser
(10 filer / 500 linjer): en endring trenger ikke sprenge budsjettet for å være
for stor til at én leser kan se hele den. T5 er der en selvsikker feil koster
mest, fordi den svekker alle senere dømmekraft-sjekker samtidig.

`confidence` finnes allerede i `faber_live_adapter`s JSON-kontrakt, men stopper
der: `ReviewEvidence` har i dag bare `verdict`, `diff_id` og `reviewer`, så steg
10 kan ikke lese den. **Del 2 legger til `ReviewEvidence.confidence`** (default
`None` = umålt = utløser). Fram til da får kjeden ingen selvrapport å lese, og
T2 (`confidence_unmeasured`) vil derfor fyre på alt — hvilket er riktig
retning, men verdt å vite før del 2 landes.

## Beslutning 3 — hva skjer ved uenighet

En andre mening som overstyres i stillhet er dekorasjon. Valget er **asymmetrisk**
og ligger i `resolve_disagreement`:

| Reviewer | Second opinion | Utfall | Gate |
|----------|----------------|--------|------|
| PASS | `CONCUR` | lander | `second_opinion` |
| PASS | `DISSENT` | **BLOKKERER** | `second_opinion_dissent` |
| PASS | `ESCALATE` | **BLOKKERER + til Morten** | `second_opinion_escalate` |
| PASS | intet brukbart svar | **BLOKKERER** | `second_opinion_unavailable` |
| ikke-PASS | `CONCUR` | blokkerer fortsatt | `second_opinion_cannot_upgrade` |

Tre ting er valgt her, og hvert av dem kunne vært valgt motsatt:

1. **Uenighet blokkerer nedover.** Kostnaden er asymmetrisk: å blokkere før
   landing er billig og reversibelt; å lande en gal endring er ingen av delene.
   Alternativet — «loggfør begge stemmer og land likevel» — ble forkastet fordi
   det gjør andre-meningen til dekorasjon, som er nøyaktig defekten den skulle
   fjerne.
2. **Enighet løfter aldri oppover.** En second opinion kan nedlegge veto, men
   aldri stemple. Uten den regelen blir andre-meningen en ankeinstans
   produsenten kan kjøre til den vinner — og da måler den viljestyrke, ikke
   kvalitet.
3. **ESCALATE går til Morten**, via `owner_gate`-mekanikken kjeden allerede har.
   Vurdereren bestemmer ikke selv; den har lov til å si «dette er ikke mitt å
   avgjøre».

**Loggføring er ikke uenighetspolitikken — den er ubetinget.** `Resolution.votes`
bærer alltid begge stemmer, også ved enighet. Å skrive dem inn i
`GovernedRunResult`-evidensen er **del 2**; i dag returnerer GUI-ruta dem i
`votes`-feltet. En enighet uten spor er ikke etterprøvbar, og da
vet man ikke om gaten kjørte i det hele tatt.

## Beslutning 4 — fail-closed

API-kallet feiler, timer ut, blir avvist av modellens sikkerhetsklassifikator,
returnerer ugyldig JSON, blir kuttet på `max_tokens`, eller returnerer en
`DISSENT` uten begrunnelse → **`UNAVAILABLE`, og det er ikke en bestått second
opinion.**

Regelen står allerede tre andre steder i denne kjeden, og denne gaten arver den
med vilje:

- `LandingScopeGate` — tomt landingssett blokkerer.
- `ScopeBudget`-kallet på steg 8 — umålt blast-radius blokkerer.
- `faber_observe._resolve_lease_clear` — uverifisert lease er ikke «clear».

`UNAVAILABLE` har sin **egen gate-verdi**, forskjellig fra `DISSENT`. Begge
blokkerer, men «vurdereren var uenig» og «vi fikk ikke svar» krever helt ulike
inngrep, og en felles «second opinion failed» ville gjort dem umulige å skille i
journalen.

**Hvorfor fail-closed er til å leve med her:** fordi utløseren er smal. En liten,
høy-confidence endring lander uten å røre API-et i det hele tatt. Hadde gaten
fyrt på alt, ville et Anthropic-utfall stanset all landing, noen ville lagt inn
en bypass — og bypassen ville vært defekten.

## Beslutning 5 — API-nøkkelen

Aldri hardkodet. Leses fra fil med **modus 0600 og eier-sjekk**
(`second_opinion_client._read_key_file`).

Modus-mønsteret er `apis/unified_api/routers/surface_receipt.py::_configured_tokens`
på `.13`: feil modus behandles som **ingen konfigurasjon**, ikke som «bruk den
likevel».

Eier-sjekken er der på grunn av `faber_observe._resolve_lease_clear`:

> En verifisering kan ikke avhenge av et kreditiv den verifiserte parten
> kontrollerer, og må aldri feile åpent til dens påstand.

En modus-sjekk alene spør om filas rettigheter, ikke hvem som satte dem: en fil
en **annen** part eier og selv har chmod-et til 0600 består den fint. Derfor
kreves også `st_uid == geteuid()` (eller root).

Env-variabel for selve nøkkelen er bevisst ikke støttet — en env-var er enda
lettere for produsent-prosessen å sette enn en fil er å endre, så en
env-fallback ville gjenopprettet nettopp fallback-hullet ADR-062 stengte. Bare
**stien** kan overstyres (`SECOND_OPINION_API_KEY_FILE`), slik at modus- og
eier-sjekken alltid kjører på det som faktisk leses.

### Ærlig om hva dette ikke løser

Faber og dashboardet kjører **begge som `agent`** på `.15`. Samme uid betyr at
produsenten faktisk *kan* slette eller chmod-e nøkkelfila. Det er ikke en
tillitsgrense eier-sjekken kan lukke, og den påstås ikke å gjøre det.

Forsvaret ligger et annet sted: **å ødelegge nøkkelen gir ikke en PASS — den gir
`UNAVAILABLE`, som blokkerer.** Den billigste bryteren for å «skru av»
andre-meningen stopper altså kjeden i stedet for å åpne den. Det er grunnen til
at fail-closed står før nøkkelhåndtering i prioritet.

## Hvor den kalles fra

- **Håndhevelsespunktet SKAL være `GovernedCodeRunner.run`** (del 2), som siste
  gate før `landing()` — etter `landing_scope` og DoD. Rekkefølgen er valgt slik
  fordi alt foran er gratis og lokalt: en endring en mekanisk gate ville stoppet
  uansett, skal ikke først betales for med et Opus-kall. Det er der en BLOCK
  faktisk stopper noe — og fram til del 2 er landet, stopper ingenting.
- **GUI-et (`POST /api/faber/second-opinion` på `.15:9119`) rapporterer.** Det
  lar Morten kjøre en vurdering for hånd (`force: true` forbigår utløseren, men
  aldri fail-closed-reglene) og se begge stemmer. Ruta lander ingenting; den kan
  ikke gi en endring en PASS.

## Konsekvenser

- Store endringer og endringer i vaktmaskineriet kan ikke lenger lande på én
  modells PASS, uansett hvor sikker den er.
- Et Anthropic-utfall stopper landing av *de utløste* endringene. Det er
  tilsiktet, og er avgrenset av at utløseren er smal.
- Hver utløst landing koster ett Opus-kall. Tersklene er de kostnads-knappene.
- `tests/test_second_opinion.py` holder utløseren, uenighetspolitikken,
  uavhengighetssjekken, nøkkelfil-reglene og hver enkelt fail-closed-vei fast:
  **89 testtilfeller**. To mutasjonssveip er kjørt mot dem — 12/12 og 8/8
  injiserte bugs fanget, der den andre runden reintroduserte reviewers egne
  funn (se under).

## Reviewer-runde 1 — hva som faktisk var galt

Verdt å ha skrevet ned, fordi tre av funnene handlet om at uavhengigheten
*så* mekanisk ut uten å være det:

1. **Vertssjekken var en delstreng-test.** `_API_HOST not in base_url` slapp
   gjennom både `https://api.anthropic.com.cortex.lan/v1` (en sannsynlig
   feilkonfigurasjon) og `http://192.168.40.13:1234/#api.anthropic.com` —
   altså nøyaktig cortex-verten dette dokumentet utelukker. Reprodusert som
   bestått `CONCUR`. Nå parses verten (`urlsplit(...).hostname`), og
   `base_url` sendes i tillegg **eksplisitt** til klienten, så env-en ikke kan
   velge endepunkt selv om sjekken en dag svikter.
2. **Modellnavnet attesterte seg selv.** Klienten falt tilbake på navnet *vi
   spurte om* når svaret utelot sitt eget — så enhver responder som bare lot
   `model` stå tomt, fikk vårt ønskede navn skrevet inn i sin identitet. Nå er
   et manglende navn `UNAVAILABLE`.
3. **`startswith("claude-opus")` er en åpen mengde.** Den godtok
   `claude-opus-4-1-cortexproxy`. Nå matches et strengt mønster.
4. **Gaten sjekket ikke sin egen forutsetning.** Uavhengighet lå bare i
   `normalise_reply`; `resolve_disagreement` kunne godta en smuglet `CONCUR`
   med `provenance="cortex.13:1234"`. Nå håndhever den den selv.
5. **Governance-flaten (T5) var for kort** — den utelot lease-autoriteten,
   landings-eksekutoren, reviewer-adapteren og gatens egen HTTP-flate. Utvidet
   til hele maskineriet.
6. **En begrunnelsesløs `ESCALATE` ble skrevet om til `UNAVAILABLE`.** Begge
   blokkerer, men bare den ene når Morten — så omskrivingen tapte nettopp det
   signalet som skulle eskaleres. Nå kreves begrunnelse bare for `DISSENT`.

Ingen av de seks ble fanget av den første testsuiten, som hadde 12/12
mutasjonsscore. **En mutasjonsscore sier at testene fanger de bugene forfatteren
tenkte på — ikke at det ikke finnes flere.** Hvert funn har nå sin egen
regresjonstest som navngir omgåelsen reviewer faktisk reproduserte.
