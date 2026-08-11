"""Fail-closed continuation loop for the MWP/Faber closeout workflow.

The starter keeps a governed job alive across verification ticks.  It does not
create authority, execute model work, mutate Kanban, commit code, or activate a
scheduler.  A caller supplies one observable tick and explicit predicates for
completion/blocking; the starter persists only metadata-only loop readback.

The important invariant is that a successful *substep* is not completion.  The
loop continues until the supplied completion predicate says the whole closeout
is complete.  A blocker or owner gate is surfaced as a durable stop reason so a
later tick can resume from the same state.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping


class LoopStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    LIMIT_REACHED = "LIMIT_REACHED"


@dataclass(frozen=True)
class LoopPolicy:
    """Safety limits; they prevent runaway processes, not premature success."""

    max_ticks: int = 1000
    max_seconds: float | None = 3600.0
    sleep_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_ticks < 1:
            raise ValueError("max_ticks must be at least 1")
        if self.max_seconds is not None and self.max_seconds <= 0:
            raise ValueError("max_seconds must be positive when set")
        if self.sleep_seconds < 0:
            raise ValueError("sleep_seconds cannot be negative")


@dataclass(frozen=True)
class LoopReadback:
    """Metadata-only state suitable for the master coverage matrix."""

    loop_id: str
    status: LoopStatus
    ticks: int
    blocker: str = ""
    next_action: str = ""
    last_readback: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "status": self.status.value,
            "ticks": self.ticks,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "last_readback": dict(self.last_readback),
        }


@dataclass(frozen=True)
class LoopTick:
    """One caller-produced observation of the whole governed workflow."""

    readback: Mapping[str, Any]
    complete: bool = False
    blocker: str = ""
    next_action: str = ""
    continue_loop: bool = False


Tick = Callable[[int], LoopTick]


def _write_readback(path: Path, readback: LoopReadback) -> None:
    """Atomically refresh metadata-only latest state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(readback.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def start_loop(
    loop_id: str,
    tick: Tick,
    *,
    policy: LoopPolicy | None = None,
    readback_path: str | Path | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> LoopReadback:
    """Run continuation ticks until whole-job completion or an explicit stop.

    ``tick`` must observe the current state and return ``complete=True`` only
    when the *entire* governed workflow is closed.  A tick that merely finishes
    a subtask must return ``complete=False`` and the loop will continue.
    """
    if not loop_id.strip():
        raise ValueError("loop_id is required")
    policy = policy or LoopPolicy()
    started = monotonic()
    latest = LoopReadback(loop_id=loop_id, status=LoopStatus.RUNNING, ticks=0)
    if readback_path is not None:
        _write_readback(Path(readback_path), latest)

    for number in range(1, policy.max_ticks + 1):
        if policy.max_seconds is not None and monotonic() - started >= policy.max_seconds:
            latest = LoopReadback(
                loop_id=loop_id,
                status=LoopStatus.LIMIT_REACHED,
                ticks=number - 1,
                blocker="loop time limit reached before whole-job completion",
                next_action="resume from the persisted readback",
                last_readback=latest.last_readback,
            )
            break
        try:
            observation = tick(number)
        except Exception as exc:  # noqa: BLE001 - durable failure state is the contract
            latest = LoopReadback(
                loop_id=loop_id,
                status=LoopStatus.FAILED,
                ticks=number,
                blocker=f"tick failed: {type(exc).__name__}",
                next_action="inspect the failed tick and resume after repair",
                last_readback=latest.last_readback,
            )
            break

        if not isinstance(observation, LoopTick):
            raise TypeError("tick must return LoopTick")
        if observation.blocker and not observation.continue_loop:
            status = LoopStatus.BLOCKED
        elif observation.complete:
            status = LoopStatus.COMPLETE
        else:
            status = LoopStatus.RUNNING
        latest = LoopReadback(
            loop_id=loop_id,
            status=status,
            ticks=number,
            blocker=observation.blocker,
            next_action=observation.next_action,
            last_readback=dict(observation.readback),
        )
        if readback_path is not None:
            _write_readback(Path(readback_path), latest)
        if status is not LoopStatus.RUNNING:
            break
        if policy.sleep_seconds:
            sleeper(policy.sleep_seconds)
    else:
        latest = LoopReadback(
            loop_id=loop_id,
            status=LoopStatus.LIMIT_REACHED,
            ticks=policy.max_ticks,
            blocker="tick limit reached before whole-job completion",
            next_action="resume from the persisted readback",
            last_readback=latest.last_readback,
        )
        if readback_path is not None:
            _write_readback(Path(readback_path), latest)

    return latest
