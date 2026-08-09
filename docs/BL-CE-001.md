# BL-CE-001 — Evaluate cutting-edge ASI/agent patterns

**Parent MWP:** `MWP-UOSH-001`  
**CAD:** `CAD-CE-001`  
**ADR:** `ADR-CE-001`  
**Status:** Proposed evaluation backlog

| Candidate | MWP placement | First experiment |
|---|---|---|
| EvolveNet | CAD-RI / BL-RI-006, BL-RI-011 | data-local harness proposal shadow |
| PAST-Bench | CAD-RI / BL-RI-002, BL-RI-008 | memory-on/off longitudinal test |
| AgentCL | CAD-E / CAD-RI / BL-RI-002, BL-RI-008 | transfer/forgetting/interference metrics |
| EnvProbe | CAD-I / CAD-JS-WM-001 | criticality/staleness/uncertainty probe policy |
| WM-SAR | CAD-D / CAD-RI | failure-amplifier subgraph repair shadow |
| Contextual Experience Replay | CAD-E / CAD-RI | provenance-scoped experience replay |
| GATS | CAD-I / CAD-RI | layered planner quality/cost/latency benchmark |

First executable shadow child:

```text
BL-CE-MEMORY-001
→ docs/mwp-ce-memory-transfer-eval-v1.json
→ agent/mwp_memory_transfer_eval.py
→ docs/mwp-ce-memory-transfer-shadow-readback-v1.json
```

## Closeout

Each child must produce:

```text
source receipt
+ local baseline
+ isolated experiment
+ independent evaluation
+ regression result
+ cost/latency result
+ owner decision
+ promotion or discard receipt
```
