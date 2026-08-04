# Faber ↔ Hermes TUI — lukkeliste

**Eier:** Faber for kode/runtime; Morten for godkjenning og hard-limits; Claude for landing-gate.
**Scope:** Hermes/Faber/TUI-loop på `.15`.
**Eksplisitt grense:** AGI og EFC er separate systemer. Ingen AGI-artifakter, Brain/selfstate eller closeout skal skrives inn i EFC.

## Statusregel

Et punkt kan bare merkes `[x]` når implementasjon, relevant test, autoritativ readback, reviewer-gate, runtime smoke og rollback-evidens finnes. `PARTIAL`, `SHADOW` og `PASS_WITH_REQUIRED_FOLLOWUPS` er ikke lukket.

## Allerede lukket

- [x] **Faber → Hermes TUI relay-auth**
  - Commit: `d2c13b495` — `BL-3610: allow authenticated Faber TUI relay path`.
  - `/api/internal/tui/emit` er loopback-only og validerer egen relay-secret.
  - Claude-review: `PASS`.
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

- [ ] **Alle coding-relevante TUI-turns inn til Faber**
  - Done når hver turn har `trace_id`, `goal_id`, owner, provenance og consent/injection-gate-readback.
  - Privat eller injection-blokkert materiale skal ikke injiseres.
- [ ] **Faber er eneste autoritative kode-runtime**
  - Done når Hermes ikke kan bygge/lande kode parallelt uten Faber-goal/livssyklus.
  - Cron, `run_agent` og pipeline må være adaptere til én autoritativ tick.
- [ ] **Live frontend-acceptance-readback**
  - Done når TUI-klientens synlige acceptance er verifisert som samme signal som backend `accept_suggestion()`.

### B. Minne — 20-lags kontrakt

- [ ] **20-lags profile-readback**
  - Done når alle 20 lag har eksplisitt status: `usable`, `empty`, `blind` eller `excluded`, med reader og årsak.
  - `20/20 selected` alene er ikke nok.
- [ ] **Per-turn memory provenance**
  - Done når Faber-readback viser valgt scope, inkluderte lag, ekskluderte lag, tokenbudsjett og ingen silent drop.
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
