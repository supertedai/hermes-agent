#!/usr/bin/env bash
set -euo pipefail

CANONICAL=/home/byopus/AGI
STAGING=/home/byopus/AGI-staging
CONTAINER=efc-unified-api

if [[ ! -d "$CANONICAL/apis/unified_api" ]]; then
  echo "canonical AGI tree missing: $CANONICAL" >&2
  exit 2
fi
if [[ ! -d "$STAGING/apis/unified_api" ]]; then
  echo "staging AGI tree missing: $STAGING" >&2
  exit 2
fi

install -m 0644 \
  "$STAGING/apis/unified_api/routers/mwp_runtime.py" \
  "$CANONICAL/apis/unified_api/routers/mwp_runtime.py"

python3 - <<'PY'
from pathlib import Path

p = Path('/home/byopus/AGI/apis/unified_api/main.py')
s = p.read_text(encoding='utf-8')
imp = 'from apis.unified_api.routers.mwp_runtime import router as mwp_runtime_router\n'
if imp not in s:
    marker = 'from apis.unified_api.routers.observability import router as observability_router\n'
    if marker not in s:
        raise SystemExit('observability import marker not found')
    s = s.replace(marker, marker + imp, 1)

lines = [line for line in s.splitlines() if 'mwp_runtime_router' not in line or line.startswith('from apis.unified_api.routers.mwp_runtime import')]
mount = 'app.include_router(mwp_runtime_router, tags=["MWP Runtime Readback"])'
for i, line in enumerate(lines):
    if line.startswith('app.include_router(gateway_router'):
        lines.insert(i, mount)
        break
else:
    raise SystemExit('gateway_router registration not found')
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('CANONICAL_SOURCE_PATCHED')
PY

sudo docker exec "$CONTAINER" python -m py_compile \
  /repo/apis/unified_api/routers/mwp_runtime.py \
  /repo/apis/unified_api/main.py

sudo docker exec "$CONTAINER" python -c \
  'import apis.unified_api.main; print("CONTAINER_IMPORT_OK")'

sudo docker restart "$CONTAINER" >/dev/null
sleep 5

python3 - <<'PY'
import json
import urllib.error
import urllib.request

url = 'http://127.0.0.1:8010/api/mwp/runtime'
try:
    with urllib.request.urlopen(url, timeout=15) as response:
        payload = json.loads(response.read().decode('utf-8'))
        print('RUNTIME_HTTP', response.status)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
except urllib.error.HTTPError as error:
    print('RUNTIME_HTTP', error.code)
    print(error.read().decode('utf-8', errors='replace'))
    raise SystemExit(1)
PY
