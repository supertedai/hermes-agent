"""Fail-closed post-creation Life Contract ↔ domain ↔ agent sync contract.

The lifecycle authority is intentionally explicit:

1. Life Contract declares the requested user/domain intent.
2. Domain provisioning creates the domain.
3. Domain provisioning creates the steward agent.
4. Only a verified domain+agent creation receipt may sync bindings back into
   the Life Contract.
5. A round-trip readback must prove that all three records point to each other.

This module is a metadata-only validator/projection. It does not create records
or grant authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class SyncStatus(str, Enum):
    INTENT_ONLY = "INTENT_ONLY"
    DOMAIN_CREATED = "DOMAIN_CREATED"
    AGENT_CREATED = "AGENT_CREATED"
    SYNCED = "SYNCED"
    BLOCKED = "BLOCKED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class LifeContractIntent:
    user_id: str
    life_contract_id: str
    domain_id: str
    steward_role: str
    contract_version: str


@dataclass(frozen=True)
class CreationReceipt:
    user_id: str
    domain_id: str
    domain_version: str
    agent_id: str
    agent_binding_key: str
    steward_role: str
    created_by: str = "domain-provisioner"

    def __post_init__(self) -> None:
        required = {
            "user_id": self.user_id,
            "domain_id": self.domain_id,
            "domain_version": self.domain_version,
            "agent_id": self.agent_id,
            "agent_binding_key": self.agent_binding_key,
            "steward_role": self.steward_role,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError("creation receipt missing: " + ", ".join(missing))
        expected = f"{self.user_id}:{self.domain_id}:{self.steward_role}"
        if self.agent_binding_key != expected:
            raise ValueError(
                f"agent binding key mismatch: expected {expected}, got {self.agent_binding_key}"
            )


@dataclass(frozen=True)
class SyncReadback:
    user_id: str
    life_contract_id: str
    domain_id: str
    agent_id: str
    agent_binding_key: str
    contract_version: str
    domain_version: str
    status: SyncStatus
    blockers: tuple[str, ...] = ()

    @property
    def synced(self) -> bool:
        return self.status is SyncStatus.SYNCED and not self.blockers


def validate_post_creation_sync(
    intent: LifeContractIntent,
    receipt: CreationReceipt | None,
    contract_record: Mapping[str, str] | None,
    domain_record: Mapping[str, str] | None,
    agent_record: Mapping[str, str] | None,
) -> SyncReadback:
    """Verify the post-creation round trip; never infer missing IDs."""
    common = {
        "user_id": intent.user_id,
        "life_contract_id": intent.life_contract_id,
        "domain_id": intent.domain_id,
        "agent_id": "",
        "agent_binding_key": "",
        "contract_version": intent.contract_version,
        "domain_version": "",
    }
    blockers: list[str] = []
    if receipt is None:
        blockers.append("domain/agent creation receipt missing")
    if contract_record is None:
        blockers.append("Life Contract post-sync readback missing")
    if domain_record is None:
        blockers.append("domain readback missing")
    if agent_record is None:
        blockers.append("agent readback missing")
    if blockers:
        return SyncReadback(status=SyncStatus.BLOCKED, blockers=tuple(blockers), **common)

    assert receipt is not None
    assert contract_record is not None
    assert domain_record is not None
    assert agent_record is not None
    common["agent_id"] = receipt.agent_id
    common["agent_binding_key"] = receipt.agent_binding_key
    common["domain_version"] = receipt.domain_version

    checks = {
        "receipt user mismatch": receipt.user_id == intent.user_id,
        "receipt domain mismatch": receipt.domain_id == intent.domain_id,
        "receipt steward mismatch": receipt.steward_role == intent.steward_role,
        "domain user mismatch": domain_record.get("user_id") == intent.user_id,
        "domain id mismatch": domain_record.get("domain_id") == intent.domain_id,
        "domain agent mismatch": domain_record.get("agent_id") == receipt.agent_id,
        "agent user mismatch": agent_record.get("user_id") == intent.user_id,
        "agent domain mismatch": agent_record.get("domain_id") == intent.domain_id,
        "agent binding mismatch": agent_record.get("agent_binding_key") == receipt.agent_binding_key,
        "contract domain mismatch": contract_record.get("domain_id") == intent.domain_id,
        "contract agent mismatch": contract_record.get("agent_id") == receipt.agent_id,
        "contract binding mismatch": contract_record.get("agent_binding_key") == receipt.agent_binding_key,
        "contract version mismatch": contract_record.get("contract_version") == intent.contract_version,
    }
    blockers.extend(name for name, passed in checks.items() if not passed)
    return SyncReadback(
        status=SyncStatus.SYNCED if not blockers else SyncStatus.CONFLICT,
        blockers=tuple(blockers),
        **common,
    )
