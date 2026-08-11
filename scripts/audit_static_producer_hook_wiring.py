#!/usr/bin/env python3
"""Static, read-only producer-hook wiring census; source evidence is not runtime proof."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path('.')
HERMES_ROOT = Path(os.environ.get('HERMES_REPO_ROOT', '/home/agent/agent-layer/hermes-agent')).expanduser()
OUT = Path('docs/mwp-static-producer-hook-wiring-audit-v1.json')
TARGETS = {
    'Hermes MemoryManager': [
        'agent-layer/hermes-agent/agent/memory_manager.py',
        'agent/memory_provider.py',
        'agent/mwp_memory_manager_receipt_adapter.py',
    ],
    'ingest/Jetstream': ['agent/mwp_ingest_contract.py', 'agent/mwp_jetstream_ingest_adapter.py', 'agent/mwp_jetstream_worldmodel_router.py'],
    'Cortex/world-model': ['agent/mwp_world_model_gates.py', 'agent/mwp_world_model_topology.py', 'agent/mwp_jetstream_worldmodel_router.py'],
    'CRUD/canonical-truth': ['agent/mwp_cross_surface_truth.py', 'agent/mwp_p2_write_preflight.py', 'agent/mwp_receipt_pipeline.py'],
    'agents/stewards/delegation': ['agent/mwp_fleet_projection.py', 'agent/mwp_orchestrator_adapter.py', 'agent/mwp_responses_adapter.py', 'agent/mwp_control_plane.py'],
    'learning/promotion': ['agent/mwp_memory_learning_gates.py', 'scripts/mwp_autoresearch_promotion_gate.py'],
    'surfaces/daemon routes': ['agent/continuous_pipeline.py', 'gateway/platforms/tui.py', 'hermes_cli', 'apps/desktop'],
}


def resolve_source(rel: str) -> Path:
    """Resolve MWP-local paths and the explicit Hermes source projection."""
    prefix = 'agent-layer/hermes-agent/'
    if rel.startswith(prefix):
        return HERMES_ROOT / rel.removeprefix(prefix)
    return ROOT / rel

def main() -> int:
    rows = []
    for name, paths in TARGETS.items():
        existing = []
        missing = []
        markers = {}
        for rel in paths:
            p = resolve_source(rel)
            if p.exists():
                existing.append(rel)
                text = p.read_text(encoding='utf-8', errors='ignore') if p.is_file() else '\n'.join(x.read_text(encoding='utf-8', errors='ignore') for x in p.rglob('*.py'))
                markers[rel] = {m: (m in text) for m in ['prefetch_all','queue_prefetch_all','sync_all','ingest','provenance','principal_id','tenant_id','rollback','read_after_write','tombstone']}
            else:
                missing.append(rel)
        rows.append({'lane':name,'source_paths_existing':existing,'source_paths_missing':missing,'markers':markers,'source_status':'SOURCE_PRESENT' if existing else 'SOURCE_MISSING','runtime_status':'UNVERIFIED','authority_status':'UNVERIFIED'})
    out={'artifact_id':'mwp-static-producer-hook-wiring-audit-v1','mwp_id':'MWP-UOSH-001','status':'STATIC_SOURCE_WIRING_RUNTIME_UNVERIFIED','mode':'read-only-source-census','lanes':rows,'policy':{'source_does_not_equal_runtime':True,'writes_allowed':False,'promotion_safe':False},'next_action':'compare source hooks with one metadata-only receipt per producer and live principal/tenant/scope readback'}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'artifact':str(OUT),'lanes':len(rows),'runtime_verified':0,'writes_allowed':False},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
