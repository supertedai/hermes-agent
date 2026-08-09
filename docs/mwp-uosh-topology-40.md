# MWP-UOSH-001 — 192.168.40.0/24 topology baseline

**Collected:** 2026-08-06
**Method:** local interface/route readback, bounded TCP probes and HTTP root probes on known service ports.
**Scope:** read-only discovery; not a vulnerability scan.

## Local host

- Host address: `192.168.40.15/24`
- Default gateway: `192.168.40.1`
- Interface: `enp3s0`
- Local dashboard: `127.0.0.1:9119` (Hermes)
- Local listeners observed: `8210`, `8642`, `9101`, SSH `22`, dashboard `9119`

## Reachable nodes and identified services

| Address | Open/observed | Identification | Evidence status |
|---|---|---|---|
| `192.168.40.11` | `22`, `8000` | SSH; service on 8000 not identified by root probe | reachable, service unknown |
| `192.168.40.12` | `22`, `80`, `8000`, `8010`, `8080` | `80` nginx; `8000` router error JSON; `8010` `unified_api`; `8080` cAdvisor | live HTTP root verified |
| `192.168.40.13` | `22`, `80`, `8000`, `8080` | `80`/`8000` `unified_api`; `8080` nginx | live HTTP root verified |
| `192.168.40.14` | `22`, `9101` | SSH; `9101` service unknown | reachable, service unknown |
| `192.168.40.15` | `22`, `8210`, `8642`, `9101`, local `9119` | local host; service names for 8210/8642/9101 require process/runtime mapping | local listener readback |

## Known Opus/Symbiose anchors

- Repository defaults and providers point to `http://192.168.40.12:8010`.
- Root response at `.12:8010`: `{"status":"ok","service":"unified_api","docs":"/docs","health":"/health"}`.
- `tools/symbiose_tools.py` and `agent/symbiose_layer_provider.py` use `.12:8010` as the default Symbiose/unified API endpoint.
- Prior source evidence mentions `.13` as a Faber/graph/runtime host; this baseline confirms `.13` exposes unified API roots but does not prove service ownership.
- Prior source evidence mentions `mnemosyne@192.168.40.11`; this baseline confirms SSH and port 8000 reachability but does not identify the service.

## Unknown / not yet proven

- Full process/container/service inventory on `.11`, `.12`, `.13`, `.14`.
- Ownership and role of every open port.
- Authentication and authorization behavior for remote APIs.
- Graph, Qdrant, embeddings and GNN process boundaries.
- Which host is canonical writer versus read-only mirror.
- Cross-host session/principal propagation.
- Whether `.12` and `.13` are active/duplicate unified API instances or different runtime roles.
- Whether `.40.00` refers to the subnet, a host alias, or a separate target identifier.

## Safety and next discovery

No remote writes, SSH logins, process restarts or configuration changes were performed. Next safe step is authenticated/read-only endpoint inventory and owner/process mapping for the identified hosts, followed by CAD/ADR/BL traceability. Do not infer service authority from an open port or a healthy root response alone.
