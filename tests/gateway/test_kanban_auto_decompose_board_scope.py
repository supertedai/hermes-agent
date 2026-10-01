"""Board scope through the auto-decompose tick.

Regression: the tick used to pin each board via the process-global
``HERMES_KANBAN_BOARD`` env var and call the decomposer without a board
kwarg, so any concurrent reader (another board's tick, a dashboard request)
could resolve the wrong board. The tick now passes ``board=`` to every
decomposer call and mutates no global state.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

from gateway import kanban_watchers_dispatcher as kwd


def _dispatcher():
    settings = kwd._DispatcherSettings(60.0, None, None, 2, 0, True, None, None)
    return kwd._KanbanDispatcher(SimpleNamespace(DEFAULT_BOARD="default"), settings)


def test_auto_decompose_tick_passes_board_explicitly_and_leaves_env_untouched(monkeypatch):
    monkeypatch.setattr(kwd, "_board_slugs", lambda kb: ["alpha", "beta"])
    monkeypatch.delenv("HERMES_KANBAN_BOARD", raising=False)
    env_before = os.environ.get("HERMES_KANBAN_BOARD")

    calls = []

    def fake_list(*, board=None, tenant=None):
        calls.append(("list", board, os.environ.get("HERMES_KANBAN_BOARD")))
        return ["t1"]

    def fake_decompose(task_id, author=None, board=None):
        calls.append(("decompose", task_id, board, os.environ.get("HERMES_KANBAN_BOARD")))
        return SimpleNamespace(ok=True, fanout=False, child_ids=None, reason=None)

    fake = SimpleNamespace(list_triage_ids=fake_list, decompose_task=fake_decompose)
    monkeypatch.setitem(sys.modules, "hermes_cli.kanban_decompose", fake)
    import hermes_cli
    monkeypatch.setattr(hermes_cli, "kanban_decompose", fake, raising=False)

    decomposed = _dispatcher().auto_decompose_tick(5)

    assert decomposed == 2
    assert calls == [
        ("list", "alpha", env_before),
        ("decompose", "t1", "alpha", env_before),
        ("list", "beta", env_before),
        ("decompose", "t1", "beta", env_before),
    ]
    assert os.environ.get("HERMES_KANBAN_BOARD") == env_before
