---
name: flyby
description: "Ta imot et løst innspill fra Morten og gjøre det til en sporbar kandidat i Symbiose-grafen — dedupliert, strukturert, og med en ferdig pakke Claude kan lande. Skriver ALDRI til git, allokerer ALDRI et BL-nummer."
version: 1.0.0
author: Symbiose (BL-3229, ADR-035)
license: intern
platforms: [linux]
metadata:
  hermes:
    tags: [Symbiose, BL, ADR, flyby, graf, governance]
    category: symbiose
    related_skills: []
---

# flyby — fra løst innspill til sporbar kandidat

Kontrakten står i **ADR-035**. Denne fila er den utførbare halvdelen. Les seksjon B og D der før du
endrer noe her.

## Når den brukes

Morten skriver noe som ikke er et spørsmål, men et **innspill**: en idé, en bekymring, et hull han
ser. Ofte innledet med «flyby», men like ofte ikke — kjennetegnet er at det peker på noe som burde
gjøres, ikke noe som skal besvares.

## Fortsettelse av store tråd-/flyby-oppslag

Når en flyby-sak kommer fra en annen tråd, skal oppslaget kjøres som en **bounded continuation** — aldri som ett bredt søk i hele chat-historikken, grafen og repoet samtidig:

1. Opprett én continuation-id med kilde-tråd-id(er).
2. Hent maksimalt én liten batch om gangen (standard: 4 metadata-poster).
3. Etter hver batch: skriv atomisk checkpoint med cursor, total, status og continuation-id.
4. Returner bare metadata-only readback: id, session-id, tittel, status, kilde og eventuell feilkode. Ikke rå innhold, intern resonnering eller store tool-resultater.
5. Ved avbrudd/timeout: last inn siste checkpoint og fortsett fra cursor. Ikke start søket på nytt og ikke gjenta en uavklart skriving blindt.
6. Stopp etter én batch per chat-turn og gi et kort mellomresultat før neste batch.

`OPEN` betyr at continuationen skal kunne resume. `COMPLETE` krever cursor==total. Manglende checkpoint eller uverifisert remote-resultat skal rapporteres som `UNVERIFIED`, ikke som tomt resultat.

Implementasjonskontrakten ligger i `agent/mwp_flyby_continuation.py`; den skal brukes av MWP-ruter som bygger flyby-status fra flere sessioner.


```
problem            hva som er galt eller mangler, i én setning
berørt             hvilke komponenter/filer/agenter
hypotese           hva som antakelig må endres
akseptansekriterier hvordan vi VET at det er løst
gate               autonomt · reviewer · Morten (hard-limit)
epistemisk status  observert · delvis verifisert · verifisert
```

**Skill mellom hva du VET og hva du ANTAR.** Et innspill er en observasjon fra Morten, ikke en
måling. Skriv det som en hypotese med et verifikasjonskrav, ikke som et faktum.

### 2. Dedupliser FØR du skriver — `flyby_dedup`

```
flyby_dedup(query="<kjernen i innspillet>")
```

Den søker **:BL**-titler og **:SelfKnowledgeFact** (`plan|decision|observation|pattern`).
ADR-ene ligger i det siste laget, som `kind='decision'` med `adrNNN`-prefiks i `key` — `:ADR` som
egen node-type finnes **ikke** i grafen (`count(:ADR)` = 0, målt 2026-08-01), så et eget ADR-lag
ville bare fått «søkt i ADR» til å se utført ut. Åpne GitHub-issues er ikke dekket: det finnes
ingen autorisert GitHub-kanal herfra, og et felt som utgir seg for å være søkt i er verre enn et
felt som sier at det ikke ble det.

Finner du en eksisterende sak: **utvid den framfor å lage en ny.** To saker om samme ting er det
øy-problemet ADR-034 advarer mot.

Svarets `searched`/`failed`/`dedup_complete` sier hvilke lag som FAKTISK kjørte. Er
`dedup_complete: false`, er «ingen treff» ikke et resultat — det er et søk som ikke ble gjort.
Skriv ikke kandidaten på det grunnlaget, og la `dedup_checked` bære nøyaktig hvilke lag som kjørte.

### 3. Skriv kandidaten — `flyby_write`

```
flyby_write(
  slug="<kort_id_a_z0_9>",
  problem="…", affected="…", hypothesis="…",
  acceptance=["…", "…"],
  gate="autonomt|reviewer|morten",
  epistemic="observert|delvis_verifisert|verifisert",
  dedup_checked="<hva flyby_dedup faktisk søkte i>",
  title="<kort, presis>",
)
```

**`kind` og `key` sender du ikke.** Serveren setter `kind='plan'` og utleder
`key = candidate_<slug>_<dato>`, og det er hele poenget: verktøyet kan skrive kandidater, ikke
hva som helst. Samme slug samme dag MERGEr til samme node (revisjon bumpes) — ikke to saker.

Ruten går til `POST /api/v1/flyby/candidate`, som kaller gaten `selfstate_write` server-side.
**Ikke bruk `symbiose_write` til dette:** den går til `/api/v1/write`, hvis typer er
`fact|memory|ownership|identity|document`. `kind=plan` matcher ingen av dem, faller til
dokument-ruten, og kandidaten havner som en `:Document` i `routing_quarantine` uten `key` og uten
`:SelfKnowledgeFact`. Det skjedde 2026-08-01, og det er grunnen til at disse to verktøyene finnes.

**Aldri rå Cypher.** Gaten finnes fordi den lenker faktumet og hindrer løse tråder.

### 4. LES TILBAKE — `verified`

Read-back er ikke lenger ditt ansvar å huske: ruten leser fakta-noden tilbake fra grafen etter
skriving og svarer `verified: true` bare når den faktisk fant den, lenket, med riktig `kind` og
ikke-tomt innhold. Feiler read-back, er svaret HTTP 500 med `UVERIFISERT`.

Svaret bærer også `commit_status`, og de tre utfallene er ikke to:

| | |
|---|---|
| `verified: true` | lagret. Si «kandidat lagret». |
| `commit_status: "not_written"` | **ikke** lagret. Si det rett ut. |
| `commit_status: "unknown"` | **uavklart** — gaten kan ha committet fakta-noden og likevel kastet på audit-steget (BL-2592), eller nettverket falt. Les etter med `graph_query`. Ikke gjett i noen retning, og ikke skriv på nytt blindt. |

Ikke gjenta kall med andre `kind`-verdier og ikke lag flere poster for å få noe til å feste seg —
da har du to halve saker i stedet for én ærlig feilmelding.

Vil du se det selv:

```
graph_query("MATCH (f:SelfKnowledgeFact {key:'candidate_<slug>_<dato>'})
             RETURN f.kind, f.who, size(f.content)")
```

### 5. Returner pakken

```
Kartlagt som:      <BL-kandidat / ADR-spørsmål / bare en observasjon>
Slug:              candidate_<slug>_<dato>
Relaterte:         <hva dedup fant>
Foreslått tittel:  <kort, presis>
ADR nødvendig:     ja/nei — JA bare hvis det finnes et VALG å ta
Gate:              autonomt / reviewer / Morten
Mangler før landing: <det Claude må gjøre>
```

## Hva du IKKE gjør — og hvorfor

| | |
|---|---|
| **Allokerer et BL-nummer** | `allocate_bl.py` er eneste kilde siden BL-391, der to strømmer håndplukket «neste BL» og kolliderte tre ganger i én sesjon. Og et nummer per løs tanke gjør hver idé til en forpliktelse. |
| **Skriver til git** | Du har ingen autorisert kanal. Det er gaten, ikke en mangel — reviewer-steget fanget over førti defekter 2026-08-01. |
| **Kaller noe «landet»** | Uten commit-hash er det en påstand. BL-3163 sa «lageret har landet» mens fem filer lå ucommittet og koden kjørte i produksjon. |
| **Oppretter en ADR** | En ADR er et VALG mellom alternativer. Finnes det bare ett fornuftig svar, er det en BL. |
| **Fyller inn en status du ikke har målt** | En importert prosent er en påstand; en opptjent er en måling. |

## Feilmoder som har skjedd, så du slipper

- **Kandidat uten dedup** → to saker om samme ting, som deretter divergerer.
- **Kandidat skrevet, aldri lest tilbake** → gaten fail-opener stille, og du melder suksess.
- **Skrevet via `symbiose_write` i stedet for `flyby_write`** → `:Document` i `routing_quarantine`,
  uten `key`, uten fakta-node. Skjedde 2026-08-01; verktøyet svarte «ok».
- **Ny `kind`-verdi prøvd fordi den forrige ikke festet** → flere halve poster og ingen ærlig
  feilmelding. Én `verified: false` er et resultat; fem forsøk er rot.
- **«Dette bør bli en ADR»** på noe uten alternativer → et beslutningsregister fullt av ikke-beslutninger.
- **Fritekst uten akseptansekriterier** → Claude kan ikke vite når den er ferdig, og lander noe annet.
- **Å si «lagt til i BL og git»** når du har skrevet en kandidat → statusene må holdes adskilt.

## Kobling videre

Når Morten sier «gjør dette til arbeid», er det Claudes tur. Claude leser kandidaten fra grafen,
allokerer BL, tar lease **og** sjekker `git status --porcelain` (to ulike signaler — en ledig lease
betyr at ingen har meldt fra, ikke at ingen jobber der), og følger statusstigen i ADR-035 seksjon D.
