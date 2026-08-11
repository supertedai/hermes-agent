"""Metadata-only master coverage matrix for MWP-UOSH.

This is a readback/projection contract, not a new authority. Existing backend,
Kanban, Faber, gateway and Desktop sources remain authoritative; callers project
only their verified metadata into this matrix.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class CoverageStatus(str, Enum):
    CONNECTED = "CONNECTED"
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    CONNECTED_GATED = "CONNECTED_GATED"
    LOCAL_BY_DESIGN = "LOCAL_BY_DESIGN"
    EXTERNAL_GATE = "EXTERNAL_GATE"
    BLOCKED_UNWIRED = "BLOCKED_UNWIRED"
    BASELINE_BLOCKED = "BASELINE_BLOCKED"
    OPEN = "OPEN"


_TERMINAL_OPEN = frozenset(
    {
        CoverageStatus.BLOCKED_UNWIRED,
        CoverageStatus.BASELINE_BLOCKED,
        CoverageStatus.EXTERNAL_GATE,
        CoverageStatus.OPEN,
    }
)
_REQUIRED = (
    "surface",
    "control",
    "authority",
    "route",
    "scope",
    "readback",
    "rollback",
    "test",
    "status",
)


@dataclass(frozen=True)
class CoverageRow:
    surface: str
    control: str
    authority: str
    route: str
    scope: str
    readback: str
    rollback: str
    test: str
    status: CoverageStatus

    def __post_init__(self) -> None:
        values = {
            "surface": self.surface,
            "control": self.control,
            "authority": self.authority,
            "route": self.route,
            "scope": self.scope,
            "readback": self.readback,
            "rollback": self.rollback,
            "test": self.test,
        }
        missing = tuple(name for name, value in values.items() if not value.strip())
        if missing:
            raise ValueError("missing coverage fields: " + ", ".join(missing))
        if self.status is CoverageStatus.CONNECTED and "readback" not in self.readback.lower():
            raise ValueError("CONNECTED row must name readback evidence")

    def as_dict(self) -> dict[str, str]:
        return {
            "surface": self.surface,
            "control": self.control,
            "authority": self.authority,
            "route": self.route,
            "scope": self.scope,
            "readback": self.readback,
            "rollback": self.rollback,
            "test": self.test,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class CoverageMatrixReadback:
    matrix_id: str
    rows: tuple[CoverageRow, ...]
    status: CoverageStatus
    open_rows: int
    connected_rows: int

    @property
    def complete(self) -> bool:
        return bool(self.rows) and self.status is CoverageStatus.CONNECTED

    def as_dict(self) -> dict[str, Any]:
        return {
            "matrix_id": self.matrix_id,
            "status": self.status.value,
            "open_rows": self.open_rows,
            "connected_rows": self.connected_rows,
            "row_count": len(self.rows),
            "rows": [row.as_dict() for row in self.rows],
        }


def build_matrix(matrix_id: str, rows: Iterable[CoverageRow]) -> CoverageMatrixReadback:
    """Build deterministic metadata-only matrix readback.

    Duplicate surface/control pairs are rejected: silently merging them would
    hide contradictory authority or route claims.
    """
    if not matrix_id.strip():
        raise ValueError("matrix_id is required")
    ordered = tuple(rows)
    keys = [(row.surface, row.control) for row in ordered]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate surface/control pair in coverage matrix")
    open_rows = sum(row.status in _TERMINAL_OPEN for row in ordered)
    connected_rows = sum(row.status in {CoverageStatus.CONNECTED, CoverageStatus.CONNECTED_READ_ONLY, CoverageStatus.CONNECTED_GATED, CoverageStatus.LOCAL_BY_DESIGN} for row in ordered)
    status = CoverageStatus.CONNECTED if ordered and open_rows == 0 else CoverageStatus.OPEN
    return CoverageMatrixReadback(
        matrix_id=matrix_id,
        rows=ordered,
        status=status,
        open_rows=open_rows,
        connected_rows=connected_rows,
    )


def matrix_tick(matrix: CoverageMatrixReadback, *, blocker: str = "") -> Mapping[str, Any]:
    """Return the loop-facing projection without exposing row payloads beyond metadata."""
    return {
        "matrix_id": matrix.matrix_id,
        "status": matrix.status.value,
        "complete": matrix.complete and not blocker,
        "open_rows": matrix.open_rows,
        "connected_rows": matrix.connected_rows,
        "blocker": blocker,
    }


def validate_metadata_payload(payload: Mapping[str, Any]) -> None:
    """Reject raw evidence/code/memory payloads from a governance readback."""
    forbidden = {"raw", "raw_output", "content", "secret", "token", "code"}
    leaked = sorted(key for key in payload if key.lower() in forbidden)
    if leaked:
        raise ValueError("raw/private fields are forbidden in coverage readback: " + ", ".join(leaked))
    missing = [key for key in _REQUIRED if key not in payload]
    if missing:
        raise ValueError("coverage payload missing fields: " + ", ".join(missing))
