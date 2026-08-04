"""Read-only Symbiose canonical memory-layer status provider.

This adapter reuses the existing per-user layer measurement API. It does not
create storage or pretend that a layer-status row is memory content; blind and
pending layers remain explicit in the returned context.

BL-3621: the read is cached, refreshed off the turn path, and fail-open. It runs
inside ``before_turn``, so a raise here does not degrade a turn — it kills it
before the model is reached, and a one-word message dies exactly like a long
one. A *status* surface must not hold that much authority over the turn.
Unreachability is already a first-class state in this contract, so a slow or
dead API renders as that state — the honest answer — rather than as an
exception. Every measured row carries its age, so a cached measurement never
passes as a fresh one; a row with no measurement behind it carries no age,
because there is none to report.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agent.memory_provider import MemoryProvider

# The authoritative endpoint measures ~20 layers serially against Neo4j/Qdrant
# (~3-5s idle, tens of seconds under fleet load). Per-turn re-measurement buys
# nothing: layer *state* moves on the order of minutes, not keystrokes.
DEFAULT_TTL_SECONDS = 60.0
# Past this age a cached payload is labelled stale even while refreshes keep
# failing quietly — an outage that outlives the window must be visible.
DEFAULT_MAX_AGE_SECONDS = 300.0
# Patience is free here: the read runs on a background thread, so a long timeout
# costs a longer-lived refresh thread, never a slower turn. A short one only buys
# a cache that never fills — which is what an 8s ceiling did while the
# authoritative endpoint was taking 58-90s (BL-3621).
DEFAULT_TIMEOUT_SECONDS = 30.0


class SymbioseLayerStatusProvider(MemoryProvider):
    """Expose the authoritative 20-layer Symbiose status surface read-only."""

    def __init__(self, base_url: str | None = None, user_id: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get(
            "SYMBIOSE_MEMORY_LAYERS_API",
            "http://192.168.40.12:8010/api/v1/memory/layers",
        )).rstrip("/")
        self.user_id = user_id or os.environ.get("SYMBIOSE_MEMORY_USER", "morten")
        self._initialized = False
        self._ttl = _env_float("SYMBIOSE_MEMORY_LAYERS_TTL", DEFAULT_TTL_SECONDS)
        self._max_age = _env_float("SYMBIOSE_MEMORY_LAYERS_MAX_AGE", DEFAULT_MAX_AGE_SECONDS)
        self._timeout = _env_float("SYMBIOSE_MEMORY_LAYERS_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        self._lock = threading.Lock()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0
        self._last_error: Optional[str] = None
        self._refreshing = False

    @property
    def name(self) -> str:
        return "symbiose-layer-status"

    def is_available(self) -> bool:
        return self.base_url.startswith(("http://", "https://")) and bool(self.user_id)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self.user_id = str(kwargs.get("user_id") or self.user_id)
        self._initialized = True
        # Warm the cache at agent start, off the turn path. Agent init runs well
        # before the user types, so the first turn usually finds a measurement
        # already there — without any turn ever waiting on the network.
        self._refresh_in_background()

    def _read_layers(self) -> Dict[str, Any]:
        query = urlencode({"user": self.user_id})
        request = Request(f"{self.base_url}?{query}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self._timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Symbiose layer API returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("layers"), list):
            raise RuntimeError("Symbiose layer API returned invalid schema")
        return payload

    def _refresh(self) -> None:
        """Read once and store the outcome. Never raises.

        The `finally` is load-bearing, not defensive habit: `_refreshing` is the
        gate on every future refresh, so any exit that leaves it set freezes this
        provider for the life of the process — silently, which is the one thing
        this file's contract forbids. That includes a BaseException the `except`
        below deliberately does not catch.
        """
        try:
            try:
                payload = self._read_layers()
            except Exception as exc:  # noqa: BLE001 — a status read may not kill the turn
                with self._lock:
                    self._last_error = f"{type(exc).__name__}: {exc}"
                return
            with self._lock:
                self._cache = payload
                self._cache_at = time.monotonic()
                self._last_error = None
        finally:
            with self._lock:
                self._refreshing = False

    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        try:
            threading.Thread(
                target=self._refresh,
                name="symbiose-layer-status-refresh",
                daemon=True,
            ).start()
        except Exception as exc:  # noqa: BLE001
            # Thread exhaustion is exactly the saturated-host case this BL exists
            # for. Letting it escape would propagate out of `before_turn` and kill
            # the turn — the original bug, through a new door.
            with self._lock:
                self._refreshing = False
                self._last_error = f"{type(exc).__name__}: {exc}"

    def _current(self) -> tuple[Optional[Dict[str, Any]], float, Optional[str]]:
        """Return ``(payload, age_seconds, error)`` without ever raising or blocking.

        Every network read happens on a background thread. A warm cache inside
        the TTL is returned untouched; an expired one is returned anyway while a
        refresh runs behind it, so a slow authoritative read costs staleness
        rather than a stalled turn. With no measurement yet, the caller renders
        `unreachable` — which is what is actually known at that moment — and the
        in-flight refresh fills it in for the next turn.

        The blocking variant was tried first and measured: when the cold read
        itself times out, the cache never populates and *every* turn pays the
        full timeout. Blocking once is only cheap if it succeeds.
        """
        with self._lock:
            cache, cache_at, error = self._cache, self._cache_at, self._last_error
        if cache is None:
            self._refresh_in_background()
            return None, 0.0, error
        age = time.monotonic() - cache_at
        if age >= self._ttl:
            self._refresh_in_background()
        return cache, age, error

    def prefetch_layers(
        self,
        layers: List[str],
        query: str,
        *,
        session_id: str = "",
    ) -> Optional[Dict[str, str]]:
        payload, age, error = self._current()
        rows: Dict[str, Any] = {}
        if payload is not None:
            rows = {str(row.get("key")): row for row in payload["layers"] if isinstance(row, dict)}
        # "no payload at all" and "payload without this layer" are different
        # facts about the layer, and neither may borrow the other's reason. A
        # layer genuinely missing from a good payload stays "absent" even while a
        # refresh is failing — the stale-read error belongs to the rows that came
        # from that read, not to a row that was never in it.
        missing_reason = (
            "layer absent from authoritative response"
            if payload is not None
            else error or "no measurement yet — authoritative read in flight"
        )
        result: Dict[str, str] = {}
        for layer in layers:
            row = rows.get(layer)
            if row is None:
                result[layer] = json.dumps({
                    "key": layer,
                    "state": "unreachable",
                    "reason": missing_reason,
                }, ensure_ascii=False)
                continue
            # This is status/reader metadata, deliberately not mislabeled as content.
            entry: Dict[str, Any] = {
                "kind": "canonical_memory_layer_status",
                "key": layer,
                "state": row.get("state", "unknown"),
                "reader": row.get("reader"),
                "n": row.get("n"),
                "reason": row.get("reason") or row.get("needs"),
                "substrate": row.get("substrate"),
                "age_s": round(age, 1),
            }
            if error is not None or age >= self._max_age:
                # Served from an older read. Say that out loud rather than
                # letting a stale measurement pass as a current one.
                entry["stale"] = True
                entry["stale_reason"] = error or f"cache age {age:.0f}s exceeds max {self._max_age:.0f}s"
            result[layer] = json.dumps(entry, ensure_ascii=False)
        return result

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """This read-only status provider exposes no model tools."""
        return []

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        values = self.prefetch_layers([], query, session_id=session_id)
        return "" if values is None else ""

    def sync_turn(self, user_content: str, assistant_content: str, **kwargs: Any) -> None:
        # Read-only by contract: the authoritative writers live in Symbiose.
        return None

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        return None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
