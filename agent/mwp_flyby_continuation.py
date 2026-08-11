"""Bounded, resumable flyby continuation for MWP.

The continuation layer deliberately keeps remote search out of the chat turn's
control flow. Callers provide already-discovered metadata records, process a
small batch, persist a checkpoint atomically, and return a compact readback.
No raw payloads, model traces, or unbounded result sets are stored here.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence, cast


DEFAULT_BATCH_SIZE = 4
DEFAULT_MAX_READBACK_CHARS = 4000


@dataclass(frozen=True)
class ContinuationState:
    continuation_id: str
    source_session_ids: tuple[str, ...]
    cursor: int = 0
    total: int | None = None
    status: str = "OPEN"
    last_checkpoint: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "continuation_id": self.continuation_id,
            "source_session_ids": list(self.source_session_ids),
            "cursor": self.cursor,
            "total": self.total,
            "status": self.status,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ContinuationState":
        raw_sources = data.get("source_session_ids", ())
        raw_total = data.get("total")
        raw_cursor = data.get("cursor", 0)
        raw_status = data.get("status", "OPEN")
        raw_checkpoint = data.get("last_checkpoint")
        sources = cast(Iterable[object], raw_sources)
        return cls(
            continuation_id=str(data["continuation_id"]),
            source_session_ids=tuple(str(x) for x in sources),
            cursor=int(cast(int | str, raw_cursor)),
            total=None if raw_total is None else int(cast(int | str, raw_total)),
            status=str(raw_status),
            last_checkpoint=None if raw_checkpoint is None else str(raw_checkpoint),
        )


def initial_state(continuation_id: str, source_session_ids: Iterable[str], *, total: int | None = None) -> ContinuationState:
    """Create a bounded continuation without reading any source yet."""
    return ContinuationState(continuation_id, tuple(source_session_ids), total=total)


def load_checkpoint(path: str | Path) -> ContinuationState | None:
    target = Path(path)
    if not target.exists():
        return None
    return ContinuationState.from_dict(json.loads(target.read_text(encoding="utf-8")))


def save_checkpoint(path: str | Path, state: ContinuationState) -> Path:
    """Atomically replace a checkpoint so an interrupted turn can resume safely."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state.as_dict(), handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return target


def next_batch(
    records: Sequence[Mapping[str, object]],
    state: ContinuationState,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[tuple[Mapping[str, object], ...], ContinuationState]:
    """Return one small batch and the state that is safe to checkpoint afterward."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if state.cursor < 0 or state.cursor > len(records):
        raise ValueError("checkpoint cursor is outside the supplied record set")
    end = min(state.cursor + batch_size, len(records))
    batch = tuple(records[state.cursor:end])
    status = "COMPLETE" if end >= len(records) else "OPEN"
    updated = ContinuationState(
        continuation_id=state.continuation_id,
        source_session_ids=state.source_session_ids,
        cursor=end,
        total=len(records),
        status=status,
        last_checkpoint=state.continuation_id,
    )
    return batch, updated


def compact_readback(
    state: ContinuationState,
    batch: Iterable[Mapping[str, object]],
    *,
    max_chars: int = DEFAULT_MAX_READBACK_CHARS,
) -> str:
    """Create metadata-only readback bounded by characters, never raw content."""
    if max_chars < 256:
        raise ValueError("max_chars must be at least 256")
    items = []
    for record in batch:
        item = {
            key: record[key]
            for key in ("id", "session_id", "title", "status", "source", "error")
            if key in record
        }
        items.append(item)
    payload = {
        "continuation_id": state.continuation_id,
        "status": state.status,
        "cursor": state.cursor,
        "total": state.total,
        "source_session_ids": list(state.source_session_ids),
        "batch": items,
    }
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(rendered) <= max_chars:
        return rendered
    # Keep the envelope and omit records rather than truncating JSON or leaking raw fields.
    compact = {
        "continuation_id": state.continuation_id[:16],
        "status": state.status,
        "cursor": state.cursor,
        "total": state.total,
        "readback_truncated": True,
    }
    rendered = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(rendered) > max_chars:
        compact["continuation_id"] = "…"
        rendered = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return rendered
