# ADR — Second opinion i Fabers 13-stegs autocoder-kjede

- **BL:** BL-4055
- **Dato:** 2026-08-11
- **Status:** Vedtatt og implementert. Del 1 i `d6c7eb148`, del 2 (håndhevelsen)
  i commiten som bærer denne linjen.
- **Kode:** `agent/second_opinion.py`, `agent/second_opinion_client.py`,
  wiring i `agent/code_workflow.py` (`GovernedCodeRunner.run`, steg 10b),
  `ReviewEvidence.confidence`, `render_review_diff` i
  `agent/faber_implementer.py` (steg 8 produserer diffen steg 10b leser),
  GUI-rute `POST /api/faber/second-opinion` (`hermes_cli/web_server.py`,
  `hermes_cli/web_models.py`)
- **Tester:** `tests/test_second_opinion.py` (89 tilfeller, politikk + transport)
  og `tests/test_code_workflow.py` (10 end-to-end-vakter på den håndhevede stien)

### Hvordan denne ADR-en ble ført — verdt å lese før du siterer den

Første utkast erklærte «Vedtatt og implementert» og siterte wiring,
`ReviewEvidence.confidence` og evidens-skriving som **ikke fantes i koden**.
Reviewer felte det: `grep second_opinion agent/code_workflow.py` ga null treff.
Det er «evidence asserted rather than measured», i ADR-en for den gaten som
politiserer nettopp det.

Utkast to sa derfor eksplisitt «del 1 av 2 — ingenting håndhever dette ennå»,
og den formuleringen sto helt til `agent/code_workflow.py` var ledig og del 2
faktisk var landet og grønn. **Statuslinjen over ble endret sist, ikke først.**

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

`confidence` fantes allerede i `faber_live_adapter`s JSON-kontrakt, men stoppet
der: `ReviewEvidence` hadde bare `verdict`, `diff_id` og `reviewer`, så steg 10
kunne ikke lese den — og en utløser som ikke kan lese sitt eget signal, kan ikke
fyre. Feltet er nå lagt til med default `None`, som betyr **umålt**, ikke
«sikker».

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
bærer alltid begge stemmer, også ved enighet, og de skrives inn i målets evidens
på **begge** stier — `second_opinion_votes` finnes både på en BLOCK og på en
LANDED. GUI-ruta returnerer de samme to stemmene i `votes`-feltet.

Det siste var en ekte defekt som verifiseringen av del 2 fanget: første utkast la
stemmene bare i `evidence`-dicten, som går til `landing()`-adapteren og aldri til
målets egen evidens. Uenighet ble altså loggført, mens **enighet forsvant på den
stien som faktisk landet** — borte nettopp der man senere spør «kjørte gaten i det
hele tatt?». `test_both_votes_are_recorded_on_the_path_that_actually_LANDS`
holder det fast. En enighet uten spor er ikke etterprøvbar, og da
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

- **Håndhevelsespunktet er `GovernedCodeRunner.run`**, som siste gate før
  `landing()` — etter `landing_scope` og DoD. Rekkefølgen er valgt slik fordi alt
  foran er gratis og lokalt: en endring en mekanisk gate ville stoppet uansett,
  skal ikke først betales for med et Opus-kall. Det er der en BLOCK faktisk
  stopper noe.
- **`second_opinion=None` betyr «bruk den ekte klienten», aldri «hopp over
  steget».** Et skip-on-None ville gjort andre-meningen valgfri for den som
  konstruerer runneren — altså avskrudd av produsenten, som er nettopp defekten
  gaten finnes for. `test_a_runner_with_no_injected_reviewer_uses_the_real_one_and_fails_closed`
  vokter det.
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
  **89 testtilfeller**. `tests/test_code_workflow.py` har i tillegg **10
  end-to-end-vakter på den håndhevede stien** — AST-vakten beviser bare at gaten
  *konstrueres*, og sier det selv: «compute the verdict and discard it, and this
  test still passes».
- **Runde 3 av reviewen** felte ADR-en for tredje gang, og alltid på samme form:
  en setning som beskrev kodens oppførsel uten å ha målt den. Første gang var det
  «Vedtatt og implementert» uten wiring; andre gang «ingen produksjonskode måtte
  endres»; tredje gang «den blokkerer ikke arbeid». Alle tre var *plausible* —
  det er nettopp derfor de ikke ble fanget av å lese dem om igjen.
- **`next_step` navngir nå én handling per gate.** `resolve_disagreement` bevarer
  `opinion.gate`, så `second_opinion_credential`, `_transport`, `_input`,
  `_refusal`, `_parse`, `_independence` og `_runtime` ikke lenger kollapser til én
  verdi. Før var kjedens eneste tvetydige `next_step` her («address the finding,
  **or** restore the reviewer») — to alternativer der bare ett gjaldt, som er
  ubrukelig for en autonom loop. Sammenlign `scope_budget`s «split the change, or
  raise the budget deliberately».
- **Fire mutasjonssveip**, alle grønne: 12/12 på politikken, 8/8 der reviewer-runde
  1s funn ble reintrodusert, 6/6 på selve wiringen — inkludert «verdiktet beregnes
  og kastes», den defekten AST-vakten per sin egen docstring ikke kan se — og 4/4
  på runde 2s funn, inkludert «`landing()` hoistet over steg 10b».

## Integrasjonsgapet del 2 avdekket

Ni eksisterende tester i fire filer landet uten å oppgi `confidence`, og
blokkerte etter steg 10b. Det er ikke støy — det er samme gap BL-4029 steg 8 og
steg 11 avdekket: **kallerne må nå deklarere hvor sikre de er og hva de endrer,
før noen kan si at det er greit å lande.** Fikset i
`test_code_workflow.py`, `test_faber_landing.py`, `test_faber_runtime.py` og
`test_flyby_promote.py` ved å injisere en eksplisitt, navngitt uavhengig
vurderer — slik at en test som *lander* nå viser begge stemmene.

`faber_runtime` sendte allerede `ReviewEvidence(**payload["review"])` videre, så
`confidence` flyter gjennom av seg selv, og en default `GovernedCodeRunner()`
bruker den ekte klienten — som er riktig oppførsel i produksjon.

## Beslutning 6 — steg 8 må produsere diffen, og det er en ny egress

Andre reviewer-runde felte del 2 på noe ADR-utkastet påsto var unødvendig.
Utkastet skrev «ingen produksjonskode måtte endres». **Det var usant**, og på en
måte som gjorde gaten verdiløs: målt var det ingen produksjonssti som satte
`evidence["diff"]`. `FaberImplementer.build` er den eneste produsenten, og
nøkkelsettet dens inneholdt det ikke på noen gren.

Konsekvensen var ikke en degradert gate — det var en **vegg**. På
`faber_runtime --tick-json` ville hver utløst endring ende i
`UNAVAILABLE / second_opinion_input`, deterministisk, av en grunn som ikke hadde
noe med endringen å gjøre, med et `next_step` («address the second opinion's
finding») som viste til et funn som aldri fantes. En gate som alltid sier nei
måler ingenting; den er bare dyrere enn å ikke ha den.

`render_review_diff(pre, post)` i `agent/faber_implementer.py` lukker det.
Tre valg i den:

1. **Samme kilde som `diff_id_for` og `measure_blast_radius`** — altså de samme
   pre-imagene generatoren fikk se. Hadde teksten kommet fra en annen kilde (et
   `git diff` mot arbeidstreet), kunne reviewerens `diff_id` matche buildens mens
   teksten viste noe annet, og da beviser diff-sammenligningen på steg 10
   ingenting.
2. **Redigert før den forlater prosessen — med FORMER, ikke nøkkelord.**
   Dette er en **ny egress**: filinnhold går til `api.anthropic.com`. Det er
   implisitt i direktivet — en andre mening om en endring krever at vurdereren ser
   endringen — men det skal stå skrevet.

   Redigeringen bruker `_redact_file_content`: bare de fem leverandør-**formene**
   (`sk-`, `ghp_`, `AKIA`, JWT, PEM), samme sett som `vet()`. **Ikke** full
   `SecretPolicy`.

   Første versjon brukte full `SecretPolicy`, og ADR-en påsto her at det var
   trygt fordi «en falsk positiv koster noen tegn i det vurdereren ser — den
   blokkerer ikke arbeid». **Reviewer målte det, og det var usant.** På 558 ekte
   `.py`-filer i repoet: 146 fikk `(redacted)` sprøytet inn i legitim kode, og
   **12 blokkerte steg 8 helt**, på `gate=security`, med tilbakerulling.

   Mekanismen er verdt å ha nedskrevet fordi den ikke er åpenbar:
   `_redact` skanner råtekst, mens `_safe_evidence` avslutter med
   `assert_safe(json.dumps(payload))` — altså den JSON-**escapede** strengen.
   `model_api_key = ""` matcher ikke rått (`[^\s,}"']+` treffer `"` og feiler,
   korrekt: en tom streng er ingen hemmelighet). Serialisert blir den
   `model_api_key = \"\"`, og da leverer **escape-tegnet** den ikke-tomme verdien
   kilden ikke hadde. Verre: `_safe_evidence(evidence)` evalueres som *argument*
   til `ImplementationBlocked` på scope-stien, så den falske sikkerhets-feilen
   kastet først og skjulte den ekte årsaken — BL-4029s «journalen lagret feil
   årsak», gjeninnført av rettelsen for noe annet.

   Ironien er presis, og derfor står den her: `_redact`s egen docstring forklarer
   hvorfor nøkkelord-mønstre holdes borte fra filinnhold — «på kildekode ville den
   blokkert legitimt arbeid, så gaten ville blitt skrudd av». Jeg siterte den
   begrunnelsen i denne ADR-en og brøt den én funksjon senere.

   **Målt etter rettelsen, samme 558 filer: 0 blokkeringer, 4 filer med
   `(redacted)`** — og alle fire inneholder faktisk kreditiv-former (det er
   redigerings- og mønstermodulene selv). Det er samme oppførsel som `vet`, altså
   sanne positiver.

   Ved siden av formene kjøres én smal **literal-verdi-regel**: nøkkelord fulgt av
   `:`/`=` og en **sitert literal på ≥16 tegn**. Den er ikke `SecretPolicy`s
   nøkkelord-mønstre — de matcher en hvilken som helst ikke-tom verdi og traff
   derfor `api_key = os.environ["K"]`, som er riktig kode. Kravet om en sitert
   literal utelukker den formen ved konstruksjon.

   Ved siden av den går ett **skjema-mønster** for `Authorization: Bearer|Basic
   <token>`. Det er ikke pynt: den smale literal-regelen krever et anførselstegn
   rett før verdien, og inne i `AUTH_HEADER = "Authorization: Basic dXNl…"` — som
   er hvordan en header-konstant faktisk skrives — når den `authorization`, spiser
   `:` og mellomrommet, og finner `B` der den krevde et anførselstegn. **Det var
   det ene stedet den nye regelen regredierte mot de fulle mønstrene den
   erstattet**, funnet av reviewer. `Bearer`/`Basic` er selvidentifiserende som en
   provider-form, så mønsteret trenger ingen verdi-vakt og treffer ikke en bar
   omtale av headeren i en docstring.

   Målt på de samme 558 filene: **19 filer med redigering, null blokkeringer.**
   Alle treff er plassholdere, sentinel-konstanter eller docstring-eksempler
   (`"your-global-hmac-secret"`, `"HERMES_BACKEND_READY"`,
   `Authorization: Bearer <token>`). Bare den siterte verdien maskeres, så linjen
   er fortsatt lesbar.

   **Redigeringen må være et fikspunkt for bakstoppen**, og det er ikke gratis:
   `(redacted)` er ti tegn uten mellomrom, så skjema-mønsterets `\S{8,}` traff
   sin egen markør og blokkeringene gikk 0 → 10 i det sekundet mønsteret ble lagt
   inn. Samme klasse som F5 — en kontroll som fyrer på en artefakt av behandlingen
   i stedet for på innholdet — gjeninnført av rettelsen for F6, én runde senere.
   Lukket med en negativ lookahead, og invarianten holdes nå av
   `test_redaction_is_a_fixed_point_of_the_backstop`.

   `_safe_evidence` sjekker `diff` på **innholdet**, ikke på JSON-representasjonen
   av det: å skanne representasjonen når feltet *er* innhold er en kategorifeil.

   **Det er ett filter, ikke to.** Et tidligere utkast her skrev «en ekte nøkkel
   som slipper forbi **begge**». Bakstoppen i `_safe_evidence` bruker samme
   mønstersett som redigeringen, så den kan per konstruksjon ikke fyre på noe som
   har gått gjennom `render_review_diff` — reviewer beviste det med 4 008
   fuzz-input og null treff. Den beholdes fordi den dekker én ting: en framtidig
   produsent som setter `evidence["diff"]` uten å gå via rendereren. Det er én
   kontroll, anvendt og så spurt om igjen, og skal ikke omtales som to.

### Hva som fortsatt forlater prosessen

Dette er en ny egress til en tredjepart, så residualet skal stå skrevet og ikke
utledes av neste leser.

Målt på seks realistiske kreditiv lagt i et pre-image fanger formene +
literal-regelen alle seks (OAuth-`GOCSPX-`, DB-passord, `Basic`-literal,
Slack-token, bar hex-token, AWS **secret** access key). Det som **ikke** fanges:

- en hemmelighet uten gjenkjennelig form som står i en variabel med et navn
  utenfor nøkkelord-listen (`BLOB = "…"`),
- en hemmelighet som settes sammen i kode i stedet for å stå som literal,
- en hemmelighet kortere enn 16 tegn — men merk at skjema-mønsteret har gulv på
  **8**, så en kort bearer-token *er* dekket; grensen på 16 gjelder bare den
  siterte literal-regelen,
- et **bart** `"Bearer <token>"` uten ordet `Authorization` i nærheten — skjema-
  mønsteret er forankret på header-navnet.

**Full `SecretPolicy` ville ikke lukket tre av de fire.** Den fjerde —
en hemmelighet kortere enn 16 tegn, `password = "hunter2x"` — ville den flagget.
Presisjonen er verdt ett ord fordi det motsatte skjedde i forrige runde: en
6/6-påstand skjulte en levende regresjon mot nettopp den policyen som ble
erstattet. Å innrømme et residual som allerede står på listen koster ingenting;
å overdrive dekningen har kostet fire review-runder. Verdt å merke seg
fordi det skjærer i favør av valget: `AKIA…` matcher access-key-**ID-en**, ikke
hemmeligheten, og nøkkelord-alternasjonen traff heller ikke
`aws_secret_access_key = "…"` — `secret` følges av `_access_key`, ikke av `=`.
De fulle mønstrene var aldri sikkerhetsnettet de ser ut som; de kostet 146
blankede filer og 12 blokkerte builds for en dekning de ikke hadde.

Presisering, fordi et tidligere utkast av dette avsnittet var for bredt: det
fantes **én** form full `SecretPolicy` fanget og den smale regelen ikke —
`Authorization: Basic …` som én literal. Den er nå lukket av skjema-mønsteret
over. Uten det ville denne seksjonen vært direkte usann.

Den virkelige førstelinjen er `vet()`, som avviser en **patch** med
kreditiv-formet materiale før `build` når evidensen i det hele tatt. Redigeringen
her dekker det `vet` aldri så: pre-imaget.

3. **Ikke avkortet.** Er diffen større enn klientens grense, blokkerer klienten
   med den begrunnelsen. En avkortet diff ville gitt en vurderer som ikke *kan* se
   hele endringen — og en PASS derfra betyr ikke det den ser ut til å bety. Det er
   nøyaktig argumentet steg 8 selv er bygget på.

## Runde 2 av reviewen — tre vakthull der mutanten overlevde

Verdt å ha nedskrevet, fordi alle tre var *tester som var grønne av feil grunn*:

- **Stemmene på BLOCK-stien var uvoktet.** Oppførselen var riktig, men bare
  LANDED-halvdelen hadde en test. ADR-en lovet begge stier; én av de to setningene
  hadde dekning.
- **Rekkefølgen mellom `landing()` og steg 10b var uvoktet.** Reviewer flyttet
  `landing(evidence)` til før gaten og fikk hele suiten grønn — altså en commit som
  skjer, og *deretter* et mål som merkes BLOCKED. I produksjon er `landing`
  den ekte commiten. Nå bruker de blokkerende testene `landing=_unreachable_landing`,
  idiomet `test_flyby_promote.py` allerede eide.
- **`test_a_runner_..._fails_closed` var grønn fordi kontrollen var avskrudd.**
  Den traff standard nøkkelsti, som tilfeldigvis er tom på `.15`. Med en ekte
  nøkkel på plass ville den samme testen gjort et **fakturert** Opus-kall og så
  feilet på svaret. Nå peker den eksplisitt på en fil som ikke finnes. Det er
  gatens egen defektklasse: fravær i suksessens forkledning.

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
