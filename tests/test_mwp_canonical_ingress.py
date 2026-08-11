from agent.mwp_canonical_ingress import IngressStatus, LeaseEvidence, authorize_autocoder


def lease(task_id="t-1"):
    return LeaseEvidence(task_id, "running", True, True, True)


def test_active_parent_and_child_allow_autocoder():
    result = authorize_autocoder(task_id="child", principal_id="morten", parent=lease("parent"), child=lease("child"))
    assert result.status is IngressStatus.READY
    assert result.executor_allowed is True


def test_missing_child_lease_blocks_autocoder():
    result = authorize_autocoder(task_id="child", principal_id="morten", parent=lease("parent"), child=None)
    assert result.status is IngressStatus.BLOCKED
    assert "child" in result.blocker


def test_direct_ingress_without_principal_blocks():
    result = authorize_autocoder(task_id="child", principal_id="", parent=lease("parent"), child=lease("child"))
    assert result.status is IngressStatus.BLOCKED
    assert "principal" in result.blocker


def test_expired_or_unhearted_lease_blocks():
    expired = LeaseEvidence("child", "running", True, False, False)
    result = authorize_autocoder(task_id="child", principal_id="morten", parent=lease("parent"), child=expired)
    assert result.status is IngressStatus.BLOCKED
    assert result.executor_allowed is False
