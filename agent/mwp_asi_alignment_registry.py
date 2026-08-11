"""Metadata-only ASI alignment registry for MWP-UOSH status quo.

This registry is a projection of existing CAD/ADR/BL, git, daemon and runtime
sources. It is not a new authority and never stores raw code, evidence,
secrets, memory or payloads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from typing import Any, Iterable


class ASIStatus(str, Enum):
    LIVE_VERIFIED = "LIVE_VERIFIED"
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    PARTIAL = "PARTIAL"
    DECLARED_ONLY = "DECLARED_ONLY"
    UNVERIFIED = "UNVERIFIED"
    BLOCKED = "BLOCKED"
    DRIFTED = "DRIFTED"
    UNKNOWN = "UNKNOWN"
    OPEN = "OPEN"


@dataclass(frozen=True)
class ASIAlignmentRow:
    key: str
    asi_capability: str
    intent_refs: str
    implementation: str
    git_source: str
    daemon_or_sync: str
    service_route: str
    scope: str
    evidence: str
    freshness: str
    drift: str
    rollback_gate: str
    status: ASIStatus
    gap: str

    def __post_init__(self) -> None:
        for field_name, value in asdict(self).items():
            if field_name != "status" and not str(value).strip():
                raise ValueError(f"ASI alignment field is empty: {field_name}")

    def as_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class ASIAlignmentReadback:
    registry_id: str
    source_snapshot: str
    rows: tuple[ASIAlignmentRow, ...]

    def __post_init__(self) -> None:
        keys = [row.key for row in self.rows]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate ASI alignment key")

    @property
    def open_rows(self) -> int:
        return sum(row.status not in {ASIStatus.LIVE_VERIFIED, ASIStatus.CONNECTED_READ_ONLY} for row in self.rows)

    @property
    def status(self) -> str:
        return "COMPLETE" if self.rows and self.open_rows == 0 else "OPEN"

    def as_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "source_snapshot": self.source_snapshot,
            "status": self.status,
            "row_count": len(self.rows),
            "open_rows": self.open_rows,
            "rows": [row.as_dict() for row in self.rows],
        }


def refresh_from_topology(registry: ASIAlignmentReadback, topology: dict[str, Any]) -> ASIAlignmentReadback:
    """Refresh only topology row from a fresh metadata-only projection."""
    freshness = topology.get("freshness", {})
    drift = topology.get("drift", {})
    fresh = isinstance(freshness, dict) and freshness.get("status") == "FRESH"
    no_drift = isinstance(drift, dict) and not any(drift.get(key) for key in ("added", "removed", "changed"))
    rows = []
    for row in registry.rows:
        if row.key != "per-user-topology":
            rows.append(row)
            continue
        status = ASIStatus.DRIFTED if no_drift is False else (ASIStatus.CONNECTED_READ_ONLY if fresh else ASIStatus.UNVERIFIED)
        rows.append(ASIAlignmentRow(**{
            **row.as_dict(),
            "status": status,
            "evidence": "metadata-only topology context readback",
            "freshness": str(freshness.get("status", "UNKNOWN")),
            "drift": json.dumps(drift, sort_keys=True),
            "gap": "topology drift detected; reconcile changed items" if status is ASIStatus.DRIFTED else ("remote inventory remains partial" if status is ASIStatus.CONNECTED_READ_ONLY else "fresh topology readback unavailable"),
        }))
    return ASIAlignmentReadback(registry.registry_id, "mwp topology refresh", tuple(rows))


def build_status_quo() -> ASIAlignmentReadback:
    """Return the conservative status quo from the verified audit evidence."""
    rows = (
        ASIAlignmentRow(
            key="cad-adr-bl-intent-registry",
            asi_capability="ASI architecture intent and governance",
            intent_refs=".12 planning/cad/CAD-0..CAD-Ø; planning/ADR-042..059; BL ledger",
            implementation="CAD/ADR/BL documents and planning registry",
            git_source=".12 repo planning/ and git-deploy hygiene",
            daemon_or_sync="brain_vault_graph_sync; adr047_backfill_attribution",
            service_route="read-only file/graph inventory",
            scope="system architecture",
            evidence="static inventory: CAD=30, ADR=19, BL-related files=215",
            freshness="audit timestamp only",
            drift="not continuously reconciled",
            rollback_gate="metadata-only; no mutation",
            # External authoritative reconciliation is absent; fail closed rather
            # than leaving this gate merely declared when evaluating closeout.
            status=ASIStatus.BLOCKED,
            gap=(
                "BLOCKED; owner=external CAD/ADR/BL authority (not identified in local checkout); "
                "evidence=static inventory only (CAD=30, ADR=19, BL-related files=215), "
                "no live CAD→ADR→BL→runtime reconciliation or graph write receipt; "
                "next_action=authority owner must provide a bounded canonical alignment readback "
                "with source refs, runtime receipt and graph read-after-write before promotion"
            ),
        ),
        ASIAlignmentRow(
            key="git-deploy-daemon-status",
            asi_capability="source-of-truth and deployment integrity",
            intent_refs="ADR-043; ADR-053; docs/GIT_DEPLOY_HYGIENE.md",
            implementation="git deploy drift scripts/tests and repository mirrors",
            git_source="Mac .13 source / .12 runtime mirror",
            daemon_or_sync="efc_repo_sync_daemon; git_repo_pull_daemon; daemon_status_exporter",
            service_route="git/deploy drift checks",
            scope="installation and fleet",
            evidence="drift test families and sync daemons found; no current end-to-end readback",
            freshness="not live-verified in this registry build",
            drift="PARTIAL",
            rollback_gate="update protection and deploy drift gates",
            status=ASIStatus.PARTIAL,
            gap="source/commit/container/runtime tuple needs one live receipt",
        ),
        ASIAlignmentRow(
            key="daemon-bl-health-alignment",
            asi_capability="autonomous daemon governance",
            intent_refs="BL-183; BL-243; BL-160/161",
            implementation="daemon integration and health auditors",
            git_source=".12 tools/ daemon sources",
            daemon_or_sync="daemon_bl_integration_auditor; daemon_health_orchestrator_daemon; daemon_watchdog",
            service_route="heartbeat/watchdog/status exports",
            scope="daemon and service fleet",
            evidence="source and tests found; candidate inventory includes historical backups",
            freshness="not normalized into current registry",
            drift="UNKNOWN",
            rollback_gate="watchdog/restart policies require separate gate",
            status=ASIStatus.PARTIAL,
            gap="active-vs-archived daemon registry and live status need reconciliation",
        ),
        ASIAlignmentRow(
            key="per-user-topology",
            asi_capability="user/install/login-surface topology awareness",
            intent_refs="ADR-049; ADR-055; MWP perfect-topology contract",
            implementation="mwp_user_topology_startup scanner",
            git_source="Hermes runtime + MWP projection",
            daemon_or_sync="startup scan; future discovery/heartbeat gate",
            service_route="Life Contract, memory, learning, cognitive and host probes",
            scope="installation + login surface + user + agent",
            evidence="live Morten smoke readback; .12/.13/.14/.15 reachable; Neo4j/Qdrant/API live",
            freshness="startup/TTL snapshot only",
            drift="not continuously discovered",
            rollback_gate="BLOCKED/UNKNOWN prevents green promotion",
            status=ASIStatus.PARTIAL,
            gap="Docker/systemd/launchd/new-service discovery and drift watcher missing",
        ),
        ASIAlignmentRow(
            key="life-contract-domain-agent",
            asi_capability="user-scoped agent/domain orchestration",
            intent_refs="ADR-047 phase 5; ADR-055; BL-3624",
            implementation="Life Contract API, steward_binding, agent roster",
            git_source=".12 unified API",
            daemon_or_sync="life_contract_aggregator; user provisioning; post-creation validator",
            service_route="life-contract facts/steward-context/deploy-domain-agent",
            scope="user + domain + steward-agent",
            evidence="9 resolved domains in latest Morten readback; IOT unresolved",
            freshness="live readback",
            drift="BLOCKED",
            rollback_gate="post-creation round-trip required",
            status=ASIStatus.BLOCKED,
            gap="IOT binding and live writer/provisioner round-trip not closed",
        ),
        ASIAlignmentRow(
            key="world-model-hub-alignment",
            asi_capability="canonical shared world model",
            intent_refs="CAD/ADR ASI architecture; world_model_hub; BL world-model work",
            implementation="WorldModelExperience/WorldModelScore/world_model_hub",
            git_source=".12 tools and graph schema",
            daemon_or_sync="world-model, prediction, learning and GNN daemons",
            service_route="Neo4j graph read paths and cognitive/world-model routes",
            scope="system + user + agent",
            evidence="static graph-read references; no complete live round-trip",
            freshness="UNVERIFIED",
            drift="UNKNOWN",
            rollback_gate="read-only audit; no promotion",
            status=ASIStatus.UNVERIFIED,
            gap="canonical hub, provenance, freshness and agent source alignment not live-proven",
        ),
        ASIAlignmentRow(
            key="chat-cortex-shared-readview",
            asi_capability="chat and Cortex shared working world model",
            intent_refs="CAD/ADR ASI architecture; MWP world-model contract",
            implementation="ConversationWorkingModel and OpusWorkingMemory references",
            git_source=".12 source references",
            daemon_or_sync="memory_bus/working-memory consumers",
            service_route="no verified OpenAPI round-trip route",
            scope="login surface + user + session",
            evidence="static references only",
            freshness="UNKNOWN",
            drift="UNKNOWN",
            rollback_gate="must remain UNVERIFIED until round-trip",
            status=ASIStatus.UNVERIFIED,
            gap="chat→Cortex and Cortex→chat readback not live-proven",
        ),
        ASIAlignmentRow(
            key="lateral-agent-bus",
            asi_capability="agent-to-agent lateral coordination",
            intent_refs="ASI agent architecture target",
            implementation="candidate peer/lateral bridges only",
            git_source=".12 source references",
            daemon_or_sync="no canonical live lateral sync owner identified",
            service_route="no verified agent-bus route",
            scope="agent + user + installation/login surface",
            evidence="no live evidence found in read-only audit",
            freshness="UNKNOWN",
            drift="UNKNOWN",
            rollback_gate="no actuation until provenance/consent gate exists",
            status=ASIStatus.UNKNOWN,
            gap="canonical lateral bus contract and live evidence missing",
        ),
        ASIAlignmentRow(
            key="asi-control-spine",
            asi_capability="end-to-end ASI progress control",
            intent_refs="CAD/ADR/BL aggregate target",
            implementation="MWP registry and continuation matrix",
            git_source="MWP projection of authoritative sources",
            daemon_or_sync="no single control-plane sync daemon yet",
            service_route="metadata-only MWP readback",
            scope="system + installation + login surface + user + agent",
            evidence="status-quo registry created from bounded audit evidence",
            freshness="registry snapshot",
            drift="OPEN",
            rollback_gate="fail-closed continuation",
            status=ASIStatus.OPEN,
            gap="must connect CAD/ADR/BL→git→daemon→runtime→world-model→Opus evidence",
        ),
    )
    return ASIAlignmentReadback("mwp-asi-status-quo-v1", ".12 read-only CAD/ADR/BL/daemon audit", rows)
