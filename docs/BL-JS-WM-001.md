# BL-JS-WM-001 — Jetstream/Cortex/domain wiring

**Parent MWP:** `MWP-UOSH-001`  
**CAD:** `CAD-JS-WM-001`  
**ADR:** `ADR-JS-WM-001`  
**Status:** Proposed / contract implemented, live projection pending

## Child work

| BL | Scope | Acceptance |
|---|---|---|
| `BL-JS-001` | Jetstream signal envelope and provenance | source, payload, freshness and injection refs |
| `BL-JS-002` | Entropy/gap routing | high-entropy or gap-triggered decision receipt |
| `BL-JS-003` | WorldModelHub projection | canonical write/read-after-write receipt |
| `BL-JS-004` | Cortex system projection | Cortex readback with provenance/freshness |
| `BL-JS-005` | Scoped domain fan-out | explicit agent/domain targets and scope receipt |
| `BL-JS-006` | Quarantine/stale/rollback | blocked or dropped signal receipt and restore path |
| `BL-JS-007` | Jetstream→recursive-improvement scout | external pattern proposal mapped to MWP/CAD/ADR/BL |

## Current implementation

```text
agent/mwp_jetstream_worldmodel_router.py
```

This is a metadata-only routing contract. It does not yet claim live
WorldModelHub/Cortex projection.
