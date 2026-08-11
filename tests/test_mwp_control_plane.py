from agent.mwp_control_plane import (
    AUTOCODER_13_GATE_CONTRACT,
    AUTOCODER_13_STEPS,
    Axis,
    ControlTask,
    DryRunStatus,
    GateVerdict,
    IdentityMode,
    IdentityVerdict,
    TaskState,
    control_task_from_kanban,
    dependency_status,
    dry_run_13_step,
    existing_identity_snapshot,
    readback,
    readbacks,
    verification_evidence_ref,
    identity_snapshot,
)


MWP = "MWP-UOSH-001"


def task(task_id, *, state=TaskState.DISCOVERY, dependencies=(), gate="", evidence=(), rollback=""):
    return ControlTask(
        mwp_id=MWP,
        case_id="CASE-AUTONOMY-00",
        task_id=task_id,
        principal_id="morten",
        axis=Axis.SYSTEM,
        state=state,
        dependencies=tuple(dependencies),
        scope="mwp/control-plane",
        required_gate=gate,
        evidence_refs=tuple(evidence),
        rollback_ref=rollback,
        model_role="sol-design",
    )


def test_read_only_task_is_ready_without_mutating_snapshot():
    current = task("discover")
    result = readback(current, {current.task_id: current})

    assert result.gate is GateVerdict.GO_READ_ONLY
    assert result.dependency_ready
    assert result.evidence_count == 0
    assert not result.has_rollback
    assert result.next_permitted_action == "continue read-only discovery"


def test_parent_is_blocked_until_dependency_is_closed():
    child = task("child", state=TaskState.RUNNING)
    parent = task("parent", dependencies=(child.task_id,))

    result = readback(parent, {child.task_id: child, parent.task_id: parent})

    assert result.gate is GateVerdict.BLOCK
    assert not result.dependency_ready
    assert "dependency not closed: child (RUNNING)" in result.blockers


def test_missing_dependency_blocks_without_guessing():
    result = dependency_status(task("parent", dependencies=("unknown",)), {})

    assert not result.ready
    assert result.blockers == ("missing dependency: unknown",)


def test_required_gate_is_owner_gate_even_when_dependencies_are_ready():
    child = task("child", state=TaskState.CLOSED)
    gated = task("gated", dependencies=(child.task_id,), gate="identity")

    result = readback(gated, {child.task_id: child, gated.task_id: gated})

    assert result.gate is GateVerdict.OWNER_GATE
    assert result.blockers == ("identity",)


def test_blocked_states_do_not_become_ready_from_empty_dependencies():
    current = task("blocked", state=TaskState.CONFLICT)
    result = readback(current, {current.task_id: current})

    assert result.gate is GateVerdict.BLOCK
    assert "task state blocks execution: CONFLICT" in result.blockers


def test_readback_is_metadata_only_and_deterministic():
    one = task("one", state=TaskState.CLOSED, evidence=("evidence:1",), rollback="rollback:1")
    two = task("two", dependencies=(one.task_id,))

    first = readbacks((one, two))
    second = readbacks((one, two))

    assert first == second
    payload = second[1].as_dict()
    assert payload["evidence_count"] == 0
    assert payload["has_rollback"] is False
    assert "raw" not in payload


def test_duplicate_task_ids_are_rejected():
    item = task("same")

    try:
        readbacks((item, item))
    except ValueError as exc:
        assert str(exc) == "duplicate task_id in control-plane snapshot"
    else:
        raise AssertionError("duplicate task IDs must fail closed")


def test_kanban_projection_requires_explicit_principal_and_axis():
    class KanbanTask:
        id = "kanban-1"
        status = "ready"
        assignee = "luna"

    projected = control_task_from_kanban(
        KanbanTask(),
        mwp_id=MWP,
        case_id="CASE-AUTONOMY-00",
        principal_id="morten",
        axis=Axis.AGENT,
        scope="mwp/control-plane",
    )

    assert projected.task_id == "kanban-1"
    assert projected.state is TaskState.READY
    assert projected.owner == "luna"
    assert projected.principal_id == "morten"
    assert projected.axis is Axis.AGENT


def test_kanban_projection_rejects_unknown_status():
    class KanbanTask:
        id = "kanban-unknown"
        status = "mystery"

    try:
        control_task_from_kanban(
            KanbanTask(),
            mwp_id=MWP,
            case_id="CASE-AUTONOMY-00",
            principal_id="morten",
            axis=Axis.SYSTEM,
            scope="mwp/control-plane",
        )
    except ValueError as exc:
        assert str(exc) == "unsupported Kanban status: mystery"
    else:
        raise AssertionError("unknown Kanban status must fail closed")


def test_evidence_reference_keeps_ledger_authoritative_and_metadata_only():
    class Evidence:
        session_id = "session-1"
        kind = "test"
        scope = "targeted"
        canonical_command = "scripts/run_tests.sh tests/test_mwp_control_plane.py -q"
        output_summary = "raw output must not be copied"

    ref = verification_evidence_ref(Evidence(), task_id="kanban-1")

    assert ref == (
        "evidence:kanban-1:session-1:test:targeted:"
        "scripts/run_tests.sh tests/test_mwp_control_plane.py -q"
    )
    assert "raw output" not in ref


def test_13_step_gate_contract_keeps_top_level_sequence_and_explicit_gates():
    assert len(AUTOCODER_13_STEPS) == 13
    assert tuple(AUTOCODER_13_GATE_CONTRACT) == (
        "bl_gate",
        "claim_and_lease",
        "governance",
        "postcommit_readback",
    )
    assert "MissionEnvelope" in AUTOCODER_13_GATE_CONTRACT["bl_gate"]
    assert "preclaim policy" in AUTOCODER_13_GATE_CONTRACT["claim_and_lease"]
    assert "verified evidence" in AUTOCODER_13_GATE_CONTRACT["claim_and_lease"]
    assert "rollback proof" in AUTOCODER_13_GATE_CONTRACT["postcommit_readback"]


def test_evidence_reference_requires_explicit_task_and_source_fields():
    class IncompleteEvidence:
        session_id = "session-1"

    try:
        verification_evidence_ref(IncompleteEvidence(), task_id="")
    except ValueError as exc:
        assert str(exc) == "task_id is required for evidence mapping"
    else:
        raise AssertionError("missing task ID must fail closed")


def test_legacy_owner_mode_is_explicit_and_does_not_read_owner_from_missing_identity():
    result = identity_snapshot(
        client_session_id="client-legacy",
        durable_session_id="durable-legacy",
        mode=IdentityMode.LEGACY_OWNER,
        read_identity=lambda _sid: None,
        resolve_role=lambda _uid: "admin",
        user_exists=lambda _uid: True,
    )

    assert result.verdict is IdentityVerdict.LEGACY_OWNER
    assert result.principal_id == "morten"
    assert result.role == "admin"
    assert result.permitted


def test_multiuser_requires_both_session_ids_to_resolve_same_principal():
    identities = {"client": "joakim", "durable": "joakim"}
    result = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=identities.get,
        resolve_role=lambda uid: "user" if uid == "joakim" else "admin",
        user_exists=lambda uid: uid == "joakim",
        expected_principal="joakim",
    )

    assert result.verdict is IdentityVerdict.AUTHENTICATED
    assert result.principal_id == "joakim"
    assert result.role == "user"


def test_multiuser_missing_or_mismatched_identity_never_falls_back_to_morten():
    missing = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=lambda _sid: None,
        resolve_role=lambda _uid: "admin",
        user_exists=lambda _uid: True,
    )
    mismatch = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity={"client": "joakim", "durable": "morten"}.get,
        resolve_role=lambda _uid: "admin",
        user_exists=lambda _uid: True,
    )

    assert missing.verdict is IdentityVerdict.BLOCK
    assert missing.principal_id == ""
    assert mismatch.verdict is IdentityVerdict.BLOCK
    assert mismatch.principal_id == ""


def test_identity_read_error_blocks_instead_of_using_legacy_owner():
    def broken(_sid):
        raise ValueError("corrupt identity")

    result = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=broken,
        resolve_role=lambda _uid: "admin",
        user_exists=lambda _uid: True,
    )

    assert result.verdict is IdentityVerdict.BLOCK
    assert result.principal_id == ""
    assert result.blockers == ("identity read failed: ValueError",)


def _patch_existing_identity_stores(monkeypatch, tmp_path, identity_data, users):
    from hermes_cli.dashboard_auth import session_identity, user_store

    identity_file = tmp_path / "session_identity.json"
    identity_file.write_text(__import__("json").dumps(identity_data), encoding="utf-8")
    users_file = tmp_path / "users.json"
    users_file.write_text(
        __import__("json").dumps({"version": 1, "secret": "", "users": users}),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_identity, "identity_path", lambda canonical=True: identity_file)
    monkeypatch.setattr(user_store, "store_path", lambda: users_file)


def test_existing_reader_integration_resolves_joakim_from_isolated_store(monkeypatch, tmp_path):
    _patch_existing_identity_stores(
        monkeypatch,
        tmp_path,
        {
            "client-joakim": {"user_id": "joakim", "ts": 1},
            "durable-joakim": {"user_id": "joakim", "ts": 1},
        },
        [{"username": "joakim", "role": "user", "disabled": False}],
    )

    result = existing_identity_snapshot(
        client_session_id="client-joakim",
        durable_session_id="durable-joakim",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        expected_principal="joakim",
    )

    assert result.verdict is IdentityVerdict.AUTHENTICATED
    assert result.principal_id == "joakim"
    assert result.role == "user"


def test_existing_reader_integration_preserves_explicit_morten_legacy_mode(monkeypatch, tmp_path):
    _patch_existing_identity_stores(
        monkeypatch,
        tmp_path,
        {},
        [{"username": "morten", "role": "admin", "disabled": False}],
    )

    result = existing_identity_snapshot(
        client_session_id="legacy-client",
        durable_session_id="legacy-durable",
        mode=IdentityMode.LEGACY_OWNER,
    )

    assert result.verdict is IdentityVerdict.LEGACY_OWNER
    assert result.principal_id == "morten"
    assert result.role == "admin"


def test_existing_reader_integration_blocks_corrupt_and_missing_multiuser_identity(
    monkeypatch, tmp_path
):
    from hermes_cli.dashboard_auth import session_identity, user_store

    identity_file = tmp_path / "session_identity.json"
    identity_file.write_text("not-json", encoding="utf-8")
    users_file = tmp_path / "users.json"
    users_file.write_text(
        '{"version":1,"secret":"","users":[{"username":"joakim","role":"user"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(session_identity, "identity_path", lambda canonical=True: identity_file)
    monkeypatch.setattr(user_store, "store_path", lambda: users_file)

    corrupt = existing_identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
    )

    identity_file.write_text("{}", encoding="utf-8")
    missing = existing_identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
    )

    assert corrupt.verdict is IdentityVerdict.BLOCK
    assert missing.verdict is IdentityVerdict.BLOCK
    assert corrupt.principal_id == missing.principal_id == ""


def test_13_step_dry_run_has_complete_sequence_and_no_side_effects():
    current = task("dry-run")
    identity = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=lambda _sid: "joakim",
        resolve_role=lambda _uid: "user",
        user_exists=lambda _uid: True,
    )

    result = dry_run_13_step(current, {current.task_id: current}, identity)

    assert result.complete_sequence
    assert len(result.steps) == 13
    assert tuple(step.name for step in result.steps) == AUTOCODER_13_STEPS
    assert result.steps[0].status is DryRunStatus.PLANNED
    assert result.steps[7].status is DryRunStatus.NOT_EXECUTED
    assert result.steps[10].status is DryRunStatus.NOT_EXECUTED
    assert result.side_effects == ()


def test_13_step_dry_run_blocks_before_planning_on_multiuser_identity_failure():
    current = task("blocked-dry-run")
    identity = identity_snapshot(
        client_session_id="client",
        durable_session_id="durable",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        read_identity=lambda _sid: None,
        resolve_role=lambda _uid: "admin",
        user_exists=lambda _uid: True,
    )

    result = dry_run_13_step(current, {current.task_id: current}, identity)

    assert result.steps[0].status is DryRunStatus.BLOCKED
    assert all(step.status is not DryRunStatus.PLANNED for step in result.steps)
    assert result.principal_id == ""
    assert result.side_effects == ()


def test_first_read_only_dry_run_uses_existing_readers_and_never_executes_build(
    monkeypatch, tmp_path
):
    _patch_existing_identity_stores(
        monkeypatch,
        tmp_path,
        {
            "client-joakim": {"user_id": "joakim", "ts": 1},
            "durable-joakim": {"user_id": "joakim", "ts": 1},
        },
        [{"username": "joakim", "role": "user", "disabled": False}],
    )
    current = task("first-dry-run")
    identity = existing_identity_snapshot(
        client_session_id="client-joakim",
        durable_session_id="durable-joakim",
        mode=IdentityMode.AUTHENTICATED_MULTIUSER,
        expected_principal="joakim",
    )

    result = dry_run_13_step(current, {current.task_id: current}, identity)

    assert result.identity_verdict is IdentityVerdict.AUTHENTICATED
    assert result.complete_sequence
    assert result.steps[0].status is DryRunStatus.PLANNED
    assert result.steps[7].status is DryRunStatus.NOT_EXECUTED
    assert result.steps[-1].status is DryRunStatus.NOT_EXECUTED
    assert result.side_effects == ()
