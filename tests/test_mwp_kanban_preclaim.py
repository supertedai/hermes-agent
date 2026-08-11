from types import SimpleNamespace

from agent.mwp_kanban_preclaim import preclaim_policy


def test_non_mwp_task_is_left_to_existing_dispatcher():
    class Conn:
        def __init__(self):
            self.task = SimpleNamespace(id="symb:task", title="ordinary", body="", tenant=None, created_by="system")
        def execute(self, *_args):
            return []
    import hermes_cli.kanban_db as kb
    original = kb.get_task
    kb.get_task = lambda _conn, _task_id: Conn().task
    try:
        assert preclaim_policy(Conn(), "symb:task") is True
    finally:
        kb.get_task = original


def test_mwp_task_blocks_without_verified_evidence(monkeypatch):
    class Rows:
        def __iter__(self):
            return iter(())
    class Conn:
        def execute(self, *_args):
            return Rows()
    task = SimpleNamespace(
        id="mwp:task",
        title="MWP-UOSH-001 task",
        body="",
        tenant="morten",
        created_by="system",
        status="ready",
        workspace_path="mwp",
        result="",
        assignee="sol",
    )
    import hermes_cli.kanban_db as kb
    monkeypatch.setattr(kb, "get_task", lambda _conn, _task_id: task)
    verdict = preclaim_policy(Conn(), task.id)
    assert verdict[0] is False
    assert "missing evidence" in verdict[1]
