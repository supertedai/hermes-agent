# Faber ↔ Hermes TUI — lukkeliste

**Eier:** Faber for kode/runtime; Morten for godkjenning og hard-limits; Sol for design/review; Claude bare som eksplisitt final-gate når det kreves.
**Scope:** Hermes/Faber/TUI-loop på `.15`.
**Eksplisitt grense:** AGI og EFC er separate systemer. Ingen AGI-artifakter, Brain/selfstate eller closeout skal skrives inn i EFC.

## Statusregel

Et punkt kan bare merkes `[x]` når implementasjon, relevant test, autoritativ readback, **Sol Design → Sol Review → Sol PASS**, runtime smoke og rollback-evidens finnes. Claude brukes ikke som standardreviewer; Claude-kall er kun tillatt når en separat final-gate uttrykkelig krever det. `PARTIAL`, `SHADOW` og `PASS_WITH_REQUIRED_FOLLOWUPS` er ikke lukket. `[~]` = PARTIAL: arbeidet er landet og gatet, men minst én done-betingelse mangler readback — det teller som ÅPENT.

## Reviewer-rekkefølge

1. **Sol Design** — vurderer løsning, scope, risiko og reversering.
2. **Sol Review** — adversarial review av eksakt diff og tester.
3. **Sol PASS** — landingstillatelse på samme diff.
4. **Morten approval** — når hard-limit eller enactment krever det.
5. **Claude** — bare ved eksplisitt final-gate; aldri som automatisk erstatning for Sol.

## Allerede lukket

- [x] **Faber → Hermes TUI relay-auth**
  - Commit: `d2c13b495` — `BL-3610: allow authenticated Faber TUI relay path`.
  - `/api/internal/tui/emit` er loopback-only og validerer egen relay-secret.
  - Historisk landing hadde Claude-review: `PASS`; nye endringer følger Sol-first-regelen over.
- [x] **Hermetisk negativ-path-test**
  - Commit: `535ed04b4` — `BL-3611: isolate TUI negative-path relay test`.
  - Unngår at unit-test sender til live TUI-relay.
  - Målrettet suite: `20 passed`.
- [x] **Runtime-readback for relay**
  - Dashboard: `active/running`.
  - Health: HTTP `200`.
  - Før fix: relay HTTP `401`.
  - Etter fix: relay HTTP `200`, `success=true`, session `b21037f8`.
- [x] **Lease/staging/rollback for de to landingene**
  - Lease claimet før endring og frigitt etter landing.
  - Kun eksplisitte egne filer staged.
  - Rollback: `git revert d2c13b495 535ed04b4`.
- [x] **Faber memory enforcement-readback for closeout-turn**
  - `source_scope=faber.codex`.
  - `enforcement_mode=per_layer_reader`.
  - `estimated_tokens=1792`, `budget_tokens=1800`, `budget_exceeded=false`.
- [x] **Målt lokal workflow-effekt**
  - Baseline: dashboard-auth avviste Faber-relay med `401`.
  - Etter endring: relay leverte med `200` til aktiv session.
  - Validering: live smoke + 20 målrettede tester.

## Åpne — må lukkes for full TUI → Faber → læring → TUI-loop

### A. Ingress og runtime-eierskap

- [x] **Alle coding-relevante TUI-turns inn til Faber** — LUKKET, live-verifisert
  - Done når hver turn har `trace_id`, `goal_id`, owner, provenance og consent/injection-gate-readback.
  - Privat eller injection-blokkert materiale skal ikke injiseres.
  - Landet: `9ab43999f` + `efaf03a2a` + `1bf790a93` (BL-3618). `agent/faber_coding_ingress.py` stempler hver turn
    med `trace_id`, `goal_id`, `owner`, `owner_source` og provenance
    (surface/session_key/session_id/turn_index/tid), og evaluerer fem gater med eksplisitt status:
    `identity`, `relevance`, `envelope`, `injection`, `consent`.
  - Ingest feiler LUKKET (manglende grant, injection-funn eller ufullstendig envelope er aldri PASS).
    Chat feiler ÅPENT med vilje — en ingest-feil skal ikke ta ned samtalen. Faber som ENESTE
    autoritative kode-runtime er neste punkt, ikke dette.
  - Hooken står over compute-host-grenen; den grenen returnerer for isolerte turns, så en hook under
    den ville stilltiende sluttet å gate når `turn_isolation` slås på (`efaf03a2a`).
  - Blokkert materiale bæres ikke videre. Readback lagrer `text_sha256` + `text_len`, aldri teksten —
    målt: 0 treff på turn-tekst i `~/.hermes-gui/faber/coding-ingress.jsonl`.
  - Sol Design PASS · Sol Review PASS · Sol PASS (`cogito-v2-preview-deepseek-671b-moe`, live-resolvet).
  - Tester: 15 nye passerer; målrettede suiter 20–23 passed. Bred gateway-suite står på
    1527 failed / 3333 passed BÅDE med og uten diffen (pre-eksisterende brekkasje, `pytest_asyncio`
    mangler) — delta 0.
  - Live smoke mot ekte consent-/logg-stier: coding → `admitted=true`; vanlig chat →
    `not_coding_relevant`; injection-bærende turn → `injection_block`.
  - Consent: `~/.hermes-gui/faber/ingress-consent.json`, grant for `morten` scope `coding_turns`,
    Morten-dirigert. Reverserbart med `granted=false` eller ved å slette fila.
  - Rollback: `git revert 1bf790a93 efaf03a2a 9ab43999f` (hver commit verifisert: reverserer rent).
  - Audit-stiene resolves via `HERMES_HOME`, ikke hardkodet `~/.hermes-gui` (`1bf790a93`). Første
    versjon hardkodet stien, og gateway-suiten — som omdirigerer `HERMES_HOME` nettopp for at tester
    ikke skal røre levende tilstand — skrev 24 syntetiske turns rett inn i produksjonsloggen. Målt
    etter fiks: 29 linjer før suite-kjøring, 29 etter. Fallback logges, aldri stilltiende.
  - **Runtime live-verifisert:** `hermes-dashboard.service` restartet kontrollert (Morten-autorisert,
    `Restart=always`): PID 1130855 (start 18:14:02) → PID 1235983 (start 20:19:54), altså etter
    committen 19:57:07 og etter fil-mtime. Health `200`.
  - **End-to-end-bevis:** ekte TUI-sesjon `6d7b317f` produserte ingress-records kl. 20:21:10 og
    20:22:04 gjennom den levende gatewayen — ikke en syntetisk smoke.
  - **Avgrensning:** dette punktet lukker ENVELOPE + GATE. En admittert turn er stemplet og
    readback-ført, men rutes ennå ikke inn i `FaberRuntime` — det er neste punkt (Faber som eneste
    autoritative kode-runtime), og det er enactment-gated.
- [ ] **Faber er eneste autoritative kode-runtime**
  - Done når Hermes ikke kan bygge/lande kode parallelt uten Faber-goal/livssyklus.
  - Cron, `run_agent` og pipeline må være adaptere til én autoritativ tick.
- [ ] **Live frontend-acceptance-readback**
  - Done når TUI-klientens synlige acceptance er verifisert som samme signal som backend `accept_suggestion()`.

### B. Minne — 20-lags kontrakt

- [x] **20-lags profile-readback** — LUKKET, live-målt (`0787027db`, BL-3664)
  - `agent/faber_memory_readback.py` rapporterer ALLE 20 kanoniske lag i hver readback, med
    substrat-tilstand, reader, antall instanser og årsak.
  - Readbacken skiller to spørsmål som stadig blandes: (1) *holder laget noe for denne
    prinsipalen* (autoritativ Symbiose-måling) og (2) *ble det lest denne turen* (planleggerens
    valg under tokenbudsjett). Et målt lag som ikke ble lest er `budget_crowded_out` — ikke tomt,
    ikke blindt.
  - `blind`, `absent`, `no_principal`, `pending_link` og `unreported_by_authority` holdes
    adskilt; de flates aldri sammen. Uåpnbar status-API gir `unreachable` for alle 20, aldri
    `usable`.
  - Live-målt mot `:8010/api/v1/memory/layers`:
    - `morten`: `principal_exists=true`, **usable 7/20**, lest 7/20, 1792/1800 tokens —
      `{selected:4, blind:10, pending_link:1, budget_crowded_out:3, absent:2}`
    - `faber`: **`principal_exists=false`**, **usable 0/20**, lest 7/20 —
      `{no_principal:7, blind:11, absent:2}`
  - Sol Review PASS · Sol PASS. 10 målrettede tester. Rollback: `git revert 0787027db`.
- [x] **Per-turn memory provenance** — LUKKET (`0787027db`, BL-3664)
  - Readbacken viser scope (prinsipal + fase), inkluderte og ekskluderte lag, tokenbudsjett og
    estimert forbruk.
  - Ingen silent drop: test beviser at `selected ∪ excluded` er nøyaktig det kanoniske registeret
    og at snittet er tomt — et lag kan ikke forsvinne ut av en readback.

### B-funn som IKKE er lukket (avdekket av readbacken over)

- [ ] **Planleggeren er blind for substrat-tilstand**
  - Den velger på prioritet/ferskhet/kostnad, ikke på om laget kan levere noe.
  - Målt for `morten`: 3 av 7 slots brennes på lag som ikke leverer, mens 3 lag som HAR innhold
    blir budsjett-fortrengt.
  - Målt for `faber`: 7 lag leses bak en prinsipal som ikke finnes.
  - Done når valget tar substrat-tilstand som input, eller når det er dokumentert hvorfor ikke.
- [ ] **`faber` mangler prinsipal i den autoritative minneflaten**
  - Hermes-GUI viser «12/20 lag» for faber; `:8010/api/v1/memory/layers?user=faber` sier
    `principal_exists=false` og 0 målte lag. To kilder er uenige om samme spørsmål.
  - Done når det er avgjort hvilken som er autoritativ, og den andre enten samstemmer eller
    slutter å påstå et tall.
- [ ] **Validert memory write/promotion**
  - Done når commit/runtime-resultat bare promoteres til riktig minnelag etter owner-, provenance- og kvalitetssjekk.

### C. Postcommit og læring

- [ ] **Reell Faber-landed postcommit**
  - Done når én faktisk Faber-jobb har verifisert:
    `commit_closer → Brain/Change Log → selfstate → readback → smoke → rollback`.
- [ ] **Før/etter-læringsmåling**
  - Done når baseline, endring, etter-måling, konfidens og valideringsstatus er lagret med commit/goal-link.
- [ ] **Workflow-/skill-effekt**
  - Done når læringen viser målbar effekt på en senere coding-turn, eller eksplisitt blir tilbakevist.
- [ ] **Læring injisert tilbake i Hermes TUI**
  - Done når en senere TUI-turn kan lese tilbake det validerte learning-eventet med samme provenance og bruke det i Faber-routing/reasoning.

### D. Godkjenning og handling

- [ ] **Reviewer → Morten-godkjenning → handling**
  - Done når reviewer PASS, Morten-approval, enactment-gate, outcome og rollback er samme korrelerte trace.
- [ ] **Shadow/enactment-readback**
  - Done når `enacted=false` enten er legitimt begrunnet som shadow eller en eksplisitt godkjent handling er målt end-to-end.

## Ikke en del av denne lukkelisten

- AGI-vitenskapelig loop/spine.
- EFC-repo eller EFC-PR2.
- AGI-artifakter inn i EFC.
- Ukvalifisert påstand om at alle 20 minnelag har innhold.

## Closeout-evidens

- Lokal relay/learning-readback: `/home/agent/.hermes-gui/faber/closeout-bl3610-bl3611.json`.
- Memory enforcement-readback: `/home/agent/.hermes-gui/faber/memory-enforcement.json`.
- Denne listen er en **åpen lukkeliste**: relay-delen er lukket, full kognitiv loop er ikke grønnmerket før punktene over har ekte readback.
