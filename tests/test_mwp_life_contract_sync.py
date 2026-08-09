import pytest

from agent.mwp_life_contract_sync import (
    CreationReceipt,
    LifeContractIntent,
    SyncStatus,
    validate_post_creation_sync,
)


@pytest.fixture
def intent():
    return LifeContractIntent(
        user_id="morten",
        life_contract_id="lc-morten-projects-v3",
        domain_id="PROJECTS",
        steward_role="daedalus",
        contract_version="v3",
    )


def receipt():
    return CreationReceipt(
        user_id="morten",
        domain_id="PROJECTS",
        domain_version="domain-v7",
        agent_id="daedalus-morten-projects",
        agent_binding_key="morten:PROJECTS:daedalus",
        steward_role="daedalus",
    )


def records():
    return (
        {"user_id": "morten", "domain_id": "PROJECTS", "agent_id": "daedalus-morten-projects", "agent_binding_key": "morten:PROJECTS:daedalus", "contract_version": "v3"},
        {"user_id": "morten", "domain_id": "PROJECTS", "agent_id": "daedalus-morten-projects"},
        {"user_id": "morten", "domain_id": "PROJECTS", "agent_binding_key": "morten:PROJECTS:daedalus"},
    )


def test_post_creation_round_trip_is_synced(intent):
    result = validate_post_creation_sync(intent, receipt(), *records())

    assert result.status is SyncStatus.SYNCED
    assert result.synced
    assert result.agent_id == "daedalus-morten-projects"


def test_missing_creation_receipt_never_reports_synced(intent):
    result = validate_post_creation_sync(intent, None, *records())

    assert result.status is SyncStatus.BLOCKED
    assert "creation receipt missing" in result.blockers[0]


def test_wrong_user_or_agent_becomes_conflict(intent):
    contract, domain, agent = records()
    bad_domain = dict(domain, user_id="joakim")
    result = validate_post_creation_sync(intent, receipt(), contract, bad_domain, agent)

    assert result.status is SyncStatus.CONFLICT
    assert "domain user mismatch" in result.blockers


def test_contract_agent_binding_must_match_creation_receipt(intent):
    contract, domain, agent = records()
    bad_contract = dict(contract, agent_id="wrong-agent")
    result = validate_post_creation_sync(intent, receipt(), bad_contract, domain, agent)

    assert result.status is SyncStatus.CONFLICT
    assert "contract agent mismatch" in result.blockers


def test_binding_key_is_user_domain_steward_scoped():
    with pytest.raises(ValueError, match="binding key mismatch"):
        CreationReceipt(
            user_id="morten",
            domain_id="PROJECTS",
            domain_version="domain-v7",
            agent_id="daedalus-morten-projects",
            agent_binding_key="PROJECTS:daedalus",
            steward_role="daedalus",
        )
