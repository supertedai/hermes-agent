# SPEC — flåte-formen av artefakt-returen (t_dce82b62, D1–D4 fra t_7bdf74a8)

Dette er den andre av de TO formene. Den første er fork-formen, levert som
commit + PR i `supertedai/hermes-agent` (PR #15, `wt/t_dce82b62`, commit
`98083add58`, base `056547bd98`). Denne fila beskriver flåte-formen, som er
den som KJØRER, og som ikke kan landes via fork-PR-en fordi filoppdelingen er
en annen.

## Artefakter

| Fil | Hva | sha256 |
|---|---|---|
| `plattform-artefakt-flate-form.patch` | patch mot flåten | `78f659864d3e669582f07cb643f1bb719148251559abd6eec0f9ffc23b3908cb` |

Patchen rører 5 filer:

    hermes_cli/kanban_db.py            141 +/-
    hermes_cli/kanban_tools.py          58 +/-   (tools/kanban_tools.py)
    tools/kanban_tools_schemas.py       73 +/-
    tests/hermes_cli/test_kanban_db.py 164 +/-
    tests/tools/test_kanban_tools.py    87 +/-

## Treet den er uttrykt mot — og hvordan det er verifisert

Målt 2026-09-20. Skrivevakten nekter å skrive i flåten (tilsiktet), så patchen
er utviklet og prøvd i en **read-only eksport av flåten HEAD**:

    git -C /home/morten/.hermes/hermes-agent archive HEAD | tar -x -C /var/tmp/t_dce82b62-flate
    # flåten HEAD = f8e2a28d82 ; eksporten ble egen git-repo (base-commit 3267245c)

`git apply --check` er kjørt mot TO trær, begge md5-verifisert identiske med
kilden før kjøring:

| Tre | Innhold | Resultat |
|---|---|---|
| `A` = `/var/tmp/t_dce82b62-check-A` | de 5 filene hentet med `git show HEAD:<fil>` fra flåten | **`git apply --check` OK** |
| `B` = `/var/tmp/t_dce82b62-check-B` | de 5 filene kopiert fra flåtens ARBEIDSTRE | **`git apply --check` OK** |

Kommandoene (kjørt steg for steg, med md5-sammenligning per fil):

    for f in <de 5 filene>; do
      md5sum /var/tmp/t_dce82b62-check-A/$f                     # = flåten HEAD-blob
      git -C /home/morten/.hermes/hermes-agent show HEAD:$f | md5sum
    done
    cd /var/tmp/t_dce82b62-check-A && git apply --check plattform-artefakt-flate-form.patch
    cd /var/tmp/t_dce82b62-check-B && git apply --check plattform-artefakt-flate-form.patch

**Merknad om drift — dette må leses før landing:** flåtens arbeidstre står
IKKE på HEAD. `git status` viser 11 endrede, ucommittede filer, blant dem
`hermes_cli/kanban_db.py` (+40 linjer: «VERTSRETTELSE brettvalg», linje ~482)
og `tools/kanban_tools_schemas.py` (1 linje, `[],` → `["summary"],` på ~164).
Kortets linjenumre (3010-3012, 2980-2984, 3015-3024) er lest fra ARBEIDSTREET;
flåtens HEAD-blober har dem ~10 linjer tidligere. Patchen er sjekket mot begge
og er rein mot begge. Landing i flåten er et EGET steg (t_882fe4fd-mønsteret):
committen må kjøres av noen som får skrive i flåten, og driften bør avklares
først, så patchen ikke lander oppå et halvferdig arbeidstre.

## Hva flåte-formen gjør (samme beslutning, annen form)

Fork-formen og flåte-formen er ikke like i kode, fordi trærne er ulike:

| | fork-formen | flåte-formen |
|---|---|---|
| staging-funksjon | `_persist_scratch_completion_artifacts` (monolittisk) | samme navn, men leser arbeidsområdet via `kanban_db_workspace._scratch_workspace` |
| vedleggsrader | settes i `complete_task` | settes i wrapperen `_stage_completion_artifacts(..., uploaded_by=…)` |
| «review»-dør | finnes IKKE i fork-treet | `request_review(..., artifact_report=…)` + `_stage_completion_artifacts` i samme txn |
| returen | `_ok(task_id, run_id, **_artifact_report_fields(...))` | `_ok_landed(kb, conn, tid, "review"/"done", **_artifact_report_fields(...))` |
| skjema-tekst | inline i `tools/kanban_tools.py` | egen fil `tools/kanban_tools_schemas.py` (3 steder) |

Selve innholdet er identisk med fork-formen og med D1–D4:

1. `_persist_scratch_completion_artifacts` returnerer nå én oppføring per
   deklarert artefakt — `{"path", "staged", "attachment_path", "reason"}` — og
   returnerer ikke lenger stille. Aldri-staget-grunnene navngis: annen
   `workspace_kind` (worktree/dir), uadministrert scratch, manglende
   `workspace_path`, sti utenfor arbeidsområdet, sti som ikke lot seg resolve.
2. `complete_task(..., artifact_report=[...])` og
   `request_review(..., artifact_report=[...])` fyller en kallereid liste.
   All DB-atferd er uendret: payload-stiene, de stasjerte kopiene, og
   `ArtifactPreservationError` + rulling for fila-som-mangler / over taket.
3. `kanban_complete` og `kanban_request_review` svarer med `artifacts`
   (én per deklarert sti; staget → `attachment_path`, ellers `reason`) og
   `artifact_warning` bare når noe ikke ble staget. **Ingen ny hard nekt** —
   en sti utenfor arbeidsområdet er legitim og kan fortsatt lastes opp av
   varsleren fra hendelses-payloaden (kanal 2, `t_28343464` eier grensen).
4. `artifacts`-beskrivelsen i skjemaet sier forutsetningene med ord
   (scratch + administrert + sti INNENFOR) og navngir BEGGE aldri-staget-
   tilfellene (worktree; scratch-utenfor), på alle tre stedene
   (`kanban_complete`s verktøytekst, `kanban_complete.artifacts`,
   `kanban_request_review.artifacts`).

## Målt i flåte-treet (ikke påstander)

Ven: `/opt/venvs/t_dce82b62-flate` (python 3.14, deps via `.pth` mot
`/opt/venvs/t_5eacb767`-site-packages + uv-cachen; `TMPDIR=/var/tmp`).
Kjørt i `/var/tmp/t_dce82b62-flate`, med kanban-env-variablene fra
arbeidsøkta fjernet.

| Kjøring | Resultat |
|---|---|
| før (pristine eksport), 3 filer | **113 passed, 1 failed, 1 skipped** |
| etter (patchen), 3 filer | **120 passed, 1 failed, 1 skipped** |
| de 5 nye atferdsprøvene på pristine kode (koden stash’et, prøvene beholdt) | **5 failed, 2 passed** |
| de samme 5 etter patchen | **passed** |

Den ene feilen er identisk før og etter og er miljøbetinget:
`test_kanban_db.py::TestSharedBoardPaths::test_dispatcher_spawn_injects_kanban_paths_without_stale_session`
dør i `RuntimeError: cannot create restart-safe systemd scope for Kanban
worker` — ingen bruker-D-Bus i denne sandkassen. Ikke kodefeil.

Rå loggene ligger hos kortet: `flate-foer.txt`, `flate-etter.txt`,
`flate-roed.txt`.

## Det jeg ikke gjorde (sagt høyt)

- Jeg skrev ikke i flåten. Patchen er ikke landet; landing er et eget steg.
- Jeg instrumenterte ikke varsleren (kanal 2 = `t_28343464`).
- Flåtens arbeidstre har 11 ucommittede filer; jeg har ikke rørt dem og har
  ikke avgjort om de skal med i landingen. Det er et menneskeord.
- Skillet mellom de to formene er ikke slått sammen; fork-PR #15 er fork-formen,
  denne patchen er flåte-formen. Ingen av dem påstår å gjelde den andre.
