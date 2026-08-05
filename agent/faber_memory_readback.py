"""Per-turn readback of the canonical 20-layer memory contract for Faber.

Two questions get conflated whenever someone says "Faber remembers across 20
layers", and this module refuses to conflate them:

  1. **Does the layer exist and hold anything for this principal?** That is the
     authoritative Symbiose measurement (``measured`` / ``blind`` / ``absent`` /
     ``pending_link`` / ``no_principal``). It is a property of the substrate.
  2. **Was the layer actually read on THIS turn?** That is the scheduler's
     selection under a token budget. A layer can be full and still unread.

A layer that is `measured` but not selected was crowded out by the budget — not
empty, not blind. Reporting "7 of 20" without saying which of the two questions
it answers is how "20 memory layers" becomes a claim nobody checked.

The readback is fail-closed in its *claims*, not in its execution: an
unreachable status API yields ``unreachable`` for every layer, never ``usable``.
Every one of the 20 canonical layers appears in the output, always — a layer
that silently vanished from a readback is the drop the readback exists to catch.

TWO PRINCIPAL KINDS, TWO SURFACES — and asking the wrong one is not a measurement
------------------------------------------------------------------------------
The authoritative layer API answers for a ``:User`` — a human principal. Faber is
a ``:FleetAgent``, and its layers are measured on a different surface entirely
(``agent_cv``/steward readers over ``(:FleetAgent)-[:HAS_SKILL]->(:AgentSkill)``).

The first cut of this module sent every principal to the User surface. For an
agent that came back ``principal_exists: false`` and twenty rows of
``no_principal`` — which READS like "measured, and the layers are empty" when
what actually happened is "we asked a surface that cannot describe this kind of
principal". That is the same class of error the underlying API itself was
hardened against (faking absence is R0-009; faking presence is its mirror), and
it was reproduced one level up.

So the readback now resolves the principal KIND first and refuses to report
layer states it did not measure. ``surface_mismatch`` is a distinct state from
``no_principal``: the first says the question was wrong, the second says the
answer was no.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.continuous_pipeline import (
    CANONICAL_MEMORY_LAYER_IDS,
    MemoryLayerSpec,
    MemoryScheduler,
)

DEFAULT_API = "http://192.168.40.12:8010/api/v1/memory/layers"
DEFAULT_BUDGET_TOKENS = 1800
DEFAULT_PHASE = "sense"

# Substrate states that mean "this layer can supply content for this principal".
_USABLE_STATES = frozenset({"measured"})
# Everything else is a reason the layer cannot supply content, kept verbatim so
# the readback never flattens 'blind' (no per-principal reader) into 'absent'
# (no store at all) or into 'no_principal' (the principal does not exist here).
_NON_USABLE_FALLBACK = "unknown_state"

# Kinds the User-shaped layer API can describe. Anything else is not "empty" on
# that surface — it is out of its domain, and saying so is the whole point.
USER_SURFACE_KINDS = frozenset({"user"})


@dataclass(frozen=True)
class LayerReadback:
    layer_id: str
    substrate_state: str
    reader: str
    instances: int
    selected: bool
    reason: str


@dataclass(frozen=True)
class MemoryReadback:
    principal: str
    principal_exists: bool
    principal_kind: str
    phase: str
    budget_tokens: int
    estimated_tokens: int
    budget_exceeded: bool
    layers: tuple[LayerReadback, ...]
    api_error: str = ""

    @property
    def usable(self) -> int:
        return sum(1 for l in self.layers if l.substrate_state in _USABLE_STATES)

    @property
    def read_this_turn(self) -> int:
        return sum(1 for l in self.layers if l.selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "principal": self.principal,
            "principal_exists": self.principal_exists,
            "principal_kind": self.principal_kind,
            "surface_describes_principal": self.principal_kind in USER_SURFACE_KINDS,
            "phase": self.phase,
            "budget_tokens": self.budget_tokens,
            "estimated_tokens": self.estimated_tokens,
            "budget_exceeded": self.budget_exceeded,
            "canonical_layers": len(self.layers),
            "usable_for_principal": self.usable,
            "read_this_turn": self.read_this_turn,
            "api_error": self.api_error,
            "layers": [asdict(l) for l in self.layers],
        }


def fetch_layer_state(principal: str, *, api: str | None = None, timeout: float = 180.0) -> tuple[dict[str, Any], str]:
    """Read the authoritative per-principal layer measurement.

    Returns ``(payload, error)``. A failure is returned, never raised and never
    silently converted into an empty-but-fine payload: the caller must be able
    to tell "measured as blind" from "we could not look".
    """
    url = (api or os.environ.get("SYMBIOSE_MEMORY_LAYERS_API", DEFAULT_API)).rstrip("/")
    query = urllib.parse.urlencode({"user": principal})
    try:
        with urllib.request.urlopen(f"{url}?{query}", timeout=timeout) as handle:
            return json.load(handle), ""
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def default_specs() -> tuple[MemoryLayerSpec, ...]:
    """The same canonical spec set the Faber runtime schedules over."""
    return tuple(
        MemoryLayerSpec(layer_id, "symbiose.canonical") for layer_id in CANONICAL_MEMORY_LAYER_IDS
    )


def build_readback(
    principal: str,
    *,
    phase: str = DEFAULT_PHASE,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    specs: Sequence[MemoryLayerSpec] | None = None,
    payload: Mapping[str, Any] | None = None,
    api_error: str = "",
    principal_kind: str = "user",
) -> MemoryReadback:
    specs = tuple(specs or default_specs())
    selection = MemoryScheduler(specs, require_canonical=True).select(
        phase=phase, budget_tokens=budget_tokens
    )
    selected = set(selection.selected)

    rows = {}
    if payload:
        for row in payload.get("layers") or []:
            key = str(row.get("key") or "")
            if key:
                rows[key] = row

    layers: list[LayerReadback] = []
    for layer_id in CANONICAL_MEMORY_LAYER_IDS:
        row = rows.get(layer_id)
        if principal_kind not in USER_SURFACE_KINDS:
            # Wrong surface for this kind of principal. Reporting `no_principal`
            # here would dress a category error up as a measurement.
            state = "surface_mismatch"
        elif api_error:
            state = "unreachable"
        elif row is None:
            # The authoritative surface did not report a canonical layer at all.
            # That is a registry mismatch, not an empty layer, and it is louder
            # than either.
            state = "unreported_by_authority"
        else:
            state = str(row.get("state") or _NON_USABLE_FALLBACK)
        is_selected = layer_id in selected
        if state not in _USABLE_STATES:
            # Substrate reason wins over scheduling: a blind layer that the
            # scheduler happened to pick still supplies nothing.
            reason = state
        elif is_selected:
            reason = "selected"
        else:
            reason = "budget_crowded_out"
        layers.append(
            LayerReadback(
                layer_id=layer_id,
                substrate_state=state,
                reader=str((row or {}).get("reader") or ""),
                instances=int((row or {}).get("n") or 0),
                selected=is_selected,
                reason=reason,
            )
        )

    # No silent drop: the readback covers the canonical registry exactly.
    assert len(layers) == len(CANONICAL_MEMORY_LAYER_IDS)

    return MemoryReadback(
        principal=principal,
        principal_exists=bool((payload or {}).get("principal_exists", False)),
        principal_kind=principal_kind,
        phase=phase,
        budget_tokens=budget_tokens,
        estimated_tokens=selection.estimated_tokens,
        budget_exceeded=selection.budget_exceeded,
        layers=tuple(layers),
        api_error=api_error,
    )


def readback_path() -> Path:
    override = os.environ.get("HERMES_FABER_MEMORY_READBACK")
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "faber" / "memory-readback.jsonl"
    except Exception:
        return Path(os.path.expanduser("~/.hermes-gui/faber/memory-readback.jsonl"))


def record(principal: str, *, phase: str = DEFAULT_PHASE, budget_tokens: int = DEFAULT_BUDGET_TOKENS,
           log: Path | None = None, principal_kind: str = "user") -> MemoryReadback:
    payload, error = ({}, "") if principal_kind not in USER_SURFACE_KINDS else fetch_layer_state(principal)
    readback = build_readback(principal, phase=phase, budget_tokens=budget_tokens,
                              payload=payload, api_error=error, principal_kind=principal_kind)
    target = log or readback_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(readback.to_dict(), ensure_ascii=False) + "\n")
    except OSError:
        pass
    return readback


def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Per-turn 20-layer memory readback.")
    ap.add_argument("--principal", default="morten")
    ap.add_argument("--principal-kind", default="user",
                    help="user = :User (denne flaten); fleet_agent = :FleetAgent (annen flate)")
    ap.add_argument("--phase", default=DEFAULT_PHASE)
    ap.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    if args.no_record:
        payload, error = ({}, "") if args.principal_kind not in USER_SURFACE_KINDS \
            else fetch_layer_state(args.principal)
        rb = build_readback(args.principal, phase=args.phase, budget_tokens=args.budget_tokens,
                            payload=payload, api_error=error, principal_kind=args.principal_kind)
    else:
        rb = record(args.principal, phase=args.phase, budget_tokens=args.budget_tokens,
                    principal_kind=args.principal_kind)
    print(json.dumps(rb.to_dict(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
