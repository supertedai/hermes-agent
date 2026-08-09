# MWP Docker Change Gate v1

## Formål

Alle MWP-runtime-endringer skal gå gjennom én canonical flyt på Docker-host `.12`.
Dette hindrer at staging, image-lag, bind-mount og runtime får forskjellige sannheter.

```text
source candidate
  → pre-read/hash
  → canonical `/home/byopus/AGI`
  → Docker bind mount `/repo`
  → container compile/import
  → controlled restart (kun ved deploy)
  → host health/route readback
  → receipt + rollback path
```

## Canonical surfaces

| Lag | Canonical target | Regel |
|---|---|---|
| Production source | `/home/byopus/AGI` på `.12` | Eneste production source |
| Staging candidate | `/home/byopus/AGI-staging` | Kandidat, aldri implicit authority |
| Unified API container | `efc-unified-api` | `/home/byopus/AGI` → `/repo` |
| Unified API host port | `.12:8010` | Runtime health/route |
| Model router | `.12:8000` | Read-only model metadata / routed inference |
| Public surface | `https://ai.byopus.com` | Authenticated readback separat gate |

## Tillatt kommandoform

Kjør gate-scriptet på `.12`:

```bash
python3 /tmp/mwp_canonical_docker_change_gate.py \
  --mode audit \
  --files apis/unified_api/routers/mwp_runtime.py apis/unified_api/main.py
```

Audit er read-only. Den godtar ulikhet mellom staging og canonical som `DRIFT_DETECTED`,
men feiler hvis canonical og `/repo` divergerer.

Deploy krever eksplisitte filer:

```bash
python3 /tmp/mwp_canonical_docker_change_gate.py \
  --mode deploy \
  --files <relative/path.py> \
  --restart
```

Deploy-gaten:

1. Leser source/canonical/container før-state.
2. Kontrollerer at `/repo` faktisk er bind-mount fra `/home/byopus/AGI`.
3. Lager backup under `/home/byopus/AGI/.mwp-change-backups/<timestamp>/`.
4. Kopierer bare deklarerte filer.
5. Verifiserer SHA-256: source → canonical → `/repo`.
6. Kjører `py_compile` i container.
7. Restarter kun deklarert container når `--restart` er gitt.
8. Leser health og `/api/mwp/runtime` etterpå.
9. Skriver JSON receipt med rollback-path.

## Forbudt

```text
docker compose up -d                         # ikke for MWP production uten gate
kopiere direkte til /repo                     # /repo er container-view, ikke source
deploye fra AGI-staging uten hash/diff        # staging er ikke authority
endre image og anta at bind-mount følger med  # image/source kan divergere
ytre public 200/401 som runtime-authority     # krever authenticated readback
```

Compose-recreate skal behandles som en mulig route/source-regresjon. Etter enhver
Compose-recreate må gate-audit og runtime-route kjøres på nytt.

## Statuskoder

```text
AUDIT_PASS       source = canonical = /repo
DRIFT_DETECTED   source != canonical, men canonical = /repo
DEPLOY_PASS      bounded copy + compile/import + probes passerte
FAILED           hash/mount/compile/import/health feilet
BLOCKED          authority, target eller rollback-evidence mangler
```

`DRIFT_DETECTED` skal ikke auto-promoteres. Eier må velge hvilken side som er canonical
før deploy.

## Minimum receipt

En receipt må inneholde:

```text
host
source_root
canonical_root
container
repo_mount
fil-path
source SHA-256
canonical before/after SHA-256
container before/after SHA-256
compile status
restart status
health/route probes
rollback_root
verified_at
```

## Runtime-gate

For unified API er minimum readback:

```text
GET http://127.0.0.1:8010/health                 → 200
GET http://127.0.0.1:8010/api/mwp/runtime       → 200
```

`NO_ACTIVE_TURN` er korrekt fail-closed når active-turn authority ikke kan bevises.
Det skal ikke erstattes med modelliste/config som authority.

## Nåværende verifiserte avvik

```text
mwp_runtime.py: staging/canonical/container konvergerer
main.py:        staging ≠ canonical; canonical/container konvergerer
manual cortex/pre-containers: fortsatt separat launch-/topology-gate
staging container: aktiv, men ikke production authority
public broker:     separat authenticated Gate-2 readback
```
