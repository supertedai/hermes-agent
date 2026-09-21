"""Context-local state for delegate_task child execution.

A Hermes process may itself be a Kanban dispatcher worker with HERMES_KANBAN_* in
os.environ. In-process delegate_task children and cron jobs fired via
``cronjob(action="run")`` are NOT dispatcher-owned, so identity gates must fail
closed for them without mutating the process-global environment.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Mapping, MutableMapping, overload

_DELEGATED_CHILD_CONTEXT: ContextVar[bool] = ContextVar("hermes_delegated_child_context", default=False)
# Any in-process execution that is NOT the dispatcher-owned worker (cron jobs). Kept separate
# so delegate_task-specific behaviour (subprocess env scrubbing, its error strings) is unchanged.
_NON_DISPATCHER_OWNED_CONTEXT: ContextVar[bool] = ContextVar("hermes_non_dispatcher_owned_context", default=False)

DELEGATED_CHILD_ENV_MARKER = "HERMES_DELEGATED_CHILD_CONTEXT"

KANBAN_ENV_KEYS: tuple[str, ...] = (
    "HERMES_KANBAN_TASK", "HERMES_KANBAN_RUN_ID", "HERMES_KANBAN_CLAIM_LOCK",
    "HERMES_KANBAN_GOAL_MODE", "HERMES_KANBAN_GOAL_MAX_TURNS",
)

# The worker scope a process carrying it must NOT hand to a spawned cron job: the caller's
# task identity above, plus the workspace-scoped location that NAMES the caller's card —
# ``…/kanban/workspaces/t_<hex>`` by this house's convention, and that basename is a
# supported way to resolve a task id. ``KANBAN_ENV_KEYS`` alone is not enough for this
# surface: :func:`scrub_kanban_env` deliberately RETAINS location, so the lineage scrub
# already removes identity while leaving the card's id sitting in
# ``HERMES_KANBAN_WORKSPACE``. The board pointer (``HERMES_KANBAN_DB`` /
# ``HERMES_KANBAN_BOARD`` / ``HERMES_KANBAN_HOME``) is board scope, not task scope, and
# stays: a job has a legitimate board, never a legitimate caller.
KANBAN_WORKER_SCOPE_KEYS: tuple[str, ...] = KANBAN_ENV_KEYS + (
    "HERMES_KANBAN_WORKSPACE", "HERMES_KANBAN_WORKSPACES_ROOT", "HERMES_KANBAN_BRANCH",
)


def carries_kanban_worker_scope(env: Mapping[str, str]) -> bool:
    """True when *env* belongs to a Kanban worker — or to a descendant of one — rather than
    to a plain session. Callers use it to tell an INHERITED worker scope from a board
    pointer a profile declared for itself."""
    return any(key in env for key in KANBAN_WORKER_SCOPE_KEYS)


def strip_kanban_worker_scope(env: Mapping[str, str]) -> dict[str, str]:
    """Return *env* without the caller's worker scope (:data:`KANBAN_WORKER_SCOPE_KEYS`).

    A pure filter: it decides nothing about *when* the scope must go, and it leaves the
    board pointer, the write fence and every secret-policy decision to its caller."""
    return {k: v for k, v in env.items() if k not in KANBAN_WORKER_SCOPE_KEYS}


def without_caller_worker_scope(env: Mapping[str, str]) -> dict[str, str]:
    """Return *env* for a spawned cron-job process: the calling process's worker scope gone.

    The process a cron job runs in is not the caller's task — it is an independent scheduled
    unit whose environment is the profile's — yet it is spawned FROM whichever process fired
    the job, and :func:`scrub_kanban_env` deliberately RETAINS location. So a hand-triggered
    run still hands the child ``HERMES_KANBAN_WORKSPACE``, whose basename is the caller's
    card id, and the child that names its task id from the environment files its ledger line
    on a card that has nothing to do with it (measurable: the deployed consumer resolves the
    task variable first and the workspace basename second). ``TERMINAL_CWD`` is that same
    dispatcher pin under another name, so it goes with the scope when it holds the same path;
    any other cwd — one a profile declares for itself — is left alone. The gate is the
    calling PROCESS, so a scheduled fire (a gateway, carrying no worker scope) is a no-op.
    """
    if not carries_kanban_worker_scope(os.environ):
        return dict(env)
    cleaned = strip_kanban_worker_scope(env)
    caller_workspace = (os.environ.get("HERMES_KANBAN_WORKSPACE") or "").rstrip("/")
    if caller_workspace and (cleaned.get("TERMINAL_CWD") or "").rstrip("/") == caller_workspace:
        cleaned.pop("TERMINAL_CWD", None)
    return cleaned


@contextmanager
def delegated_child_context(session_id: str | None = None) -> Iterator[None]:
    """Mark child execution and isolate its task-local session identity. Even a context
    entered without an id must restore the parent's session ContextVar (child
    construction calls ``set_current_session_id``)."""
    token = _DELEGATED_CHILD_CONTEXT.set(True)
    try:
        from gateway.session_context import scoped_current_session_id  # lazy: it calls is_delegated_child_context()

        with scoped_current_session_id(session_id):
            yield
    finally:
        _DELEGATED_CHILD_CONTEXT.reset(token)


def is_delegated_child_context() -> bool:
    """Return True while code is running for a delegate_task child."""
    return bool(_DELEGATED_CHILD_CONTEXT.get())


def enter_non_dispatcher_owned_context() -> Token[bool]:
    """Token form of :func:`non_dispatcher_owned_context` for long try/finally scopes."""
    return _NON_DISPATCHER_OWNED_CONTEXT.set(True)


def exit_non_dispatcher_owned_context(token: Token[bool]) -> None:
    """Restore the flag saved by :func:`enter_non_dispatcher_owned_context`."""
    _NON_DISPATCHER_OWNED_CONTEXT.reset(token)


@contextmanager
def non_dispatcher_owned_context() -> Iterator[None]:
    """Mark in-process execution that does NOT own the dispatcher's Kanban task; without it
    a cron agent run inside a worker is misread as that worker (kanban toolset force-added,
    ``kanban_complete`` defaulting to its task). ContextVar-scoped rather than clearing
    os.environ, which the worker's claim heartbeat and concurrent readers share."""
    token = enter_non_dispatcher_owned_context()
    try:
        yield
    finally:
        exit_non_dispatcher_owned_context(token)


def is_dispatcher_owned_worker_context() -> bool:
    """The single predicate every ``HERMES_KANBAN_*`` identity gate should use."""
    return not (is_delegated_child_process_context() or _NON_DISPATCHER_OWNED_CONTEXT.get())


def owned_kanban_task() -> str:
    """The board task this execution OWNS: ``HERMES_KANBAN_TASK`` for the dispatcher-owned
    worker, ``""`` otherwise. Tool access is not worker identity — a profile can expose the
    kanban toolset interactively, and children/cron runs inherit the env var — so every
    reader that turns the task id into worker behaviour (guidance, stop nudge, terminal
    outcomes) goes through this one helper."""
    if not is_dispatcher_owned_worker_context():
        return ""
    return (os.environ.get("HERMES_KANBAN_TASK") or "").strip()


def is_delegated_child_process_context() -> bool:
    """Return True in this process or a subprocess spawned by a child."""
    return bool(_DELEGATED_CHILD_CONTEXT.get()) or bool(os.environ.get(DELEGATED_CHILD_ENV_MARKER))


def _fenced_kanban_root() -> str:
    """The board root this process's Kanban lineage lives under (``kanban_home()``); ``"1"`` when it
    cannot be resolved, which readers treat as "fence every board" (the pre-path marker)."""
    try:
        from hermes_cli.kanban_db import kanban_home
        return str(kanban_home())
    except Exception:
        return "1"


def scrub_kanban_env(env: Mapping[str, str] | MutableMapping[str, str]) -> dict[str, str]:
    """Remove worker identity, retaining board/location and an inherited write fence.

    TASK absence alone would promote a descendant to an orchestrator. The marker
    survives later execs, including scripts that remove TASK themselves. This is
    cooperative runtime scoping, not confinement of code with direct SQLite access.

    The marker's value is the fenced board ROOT, so the fence applies to the lineage's
    board and not to every Kanban DB the descendant touches: a child running a repro
    against a temp ``HERMES_HOME`` got a silently read-only board there. An inherited
    path-valued marker is kept (a grandchild that moved HERMES_HOME must not re-fence
    onto its scratch root and unfence the real one).
    """
    cleaned = {k: v for k, v in env.items() if k not in KANBAN_ENV_KEYS}
    inherited = str(env.get(DELEGATED_CHILD_ENV_MARKER) or "")
    cleaned[DELEGATED_CHILD_ENV_MARKER] = inherited if inherited and inherited != "1" else _fenced_kanban_root()
    return cleaned


def kanban_path_is_fenced(path: "os.PathLike[str] | str") -> bool:
    """Whether Kanban mutations at *path* (a board DB or board-metadata root) are denied for this
    process: always for an in-process delegate child (the parent's own board); for a spawned
    descendant only when *path* is the dispatcher-pinned ``HERMES_KANBAN_DB`` or lies under the
    fenced root the marker carries. A legacy ``"1"`` marker fences everything."""
    if _DELEGATED_CHILD_CONTEXT.get():
        return True
    marker = os.environ.get(DELEGATED_CHILD_ENV_MARKER, "")
    if not marker:
        return False
    if marker == "1":
        return True
    from pathlib import Path
    target = Path(path).expanduser().resolve()
    pinned = os.environ.get("HERMES_KANBAN_DB", "").strip()
    if pinned and target == Path(pinned).expanduser().resolve():
        return True
    try:
        target.relative_to(Path(marker).expanduser().resolve())
    except ValueError:
        return False
    return True


@overload
def delegated_child_subprocess_env(env: Mapping[str, str]) -> dict[str, str]: ...


@overload
def delegated_child_subprocess_env(env: None = None) -> dict[str, str] | None: ...


def delegated_child_subprocess_env(
    env: Mapping[str, str] | MutableMapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Carry worker/delegate descendant denial across a real process spawn.

    Location and credentials are untouched; callers retain their existing secret policy.
    Dispatcher workers and supervised tool transports grant their own explicit scope.
    """
    if not (is_delegated_child_process_context() or os.environ.get("HERMES_KANBAN_TASK")
            or (env and (env.get("HERMES_KANBAN_TASK") or env.get(DELEGATED_CHILD_ENV_MARKER)))):
        return None if env is None else dict(env)
    return scrub_kanban_env(os.environ if env is None else env)
