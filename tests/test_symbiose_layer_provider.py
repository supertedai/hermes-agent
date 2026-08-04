from __future__ import annotations

import json
import time

from agent.continuous_pipeline import MemoryLayerSpec, MemoryManagerBridge, MemoryScheduler
from agent.memory_manager import MemoryManager
from agent.symbiose_layer_provider import SymbioseLayerStatusProvider


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps({
            "user": "morten",
            "principal_exists": True,
            "layers": [
                {"key": "episodisk", "state": "measured", "n": 10, "reader": "reader"},
                {"key": "kausalt", "state": "blind", "n": 0, "needs": "owner instance"},
            ],
        }).encode()


def _bridge(manager: MemoryManager) -> MemoryManagerBridge:
    specs = tuple(MemoryLayerSpec(layer, "symbiose.canonical", max_tokens=256) for layer in ("episodisk", "kausalt"))
    return MemoryManagerBridge(
        manager,
        MemoryScheduler(specs),
        strict=True,
        source_scope="faber.codex",
    )


def _manager(provider: SymbioseLayerStatusProvider) -> MemoryManager:
    manager = MemoryManager()
    manager.add_provider(provider)
    manager.initialize_all(session_id="s1", user_id="morten", platform="cli", hermes_home="/tmp")
    return manager


def _settle(provider: SymbioseLayerStatusProvider, timeout: float = 10.0) -> None:
    """Wait for any background refresh to finish."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with provider._lock:
            if not provider._refreshing:
                return
        time.sleep(0.01)
    raise AssertionError("background refresh did not settle")


def test_symbiose_layer_status_provider_preserves_measured_and_blind_state(monkeypatch):
    monkeypatch.setattr(
        "agent.symbiose_layer_provider.urlopen",
        lambda request, timeout=15: _Response(),
    )
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    manager = _manager(provider)
    _settle(provider)
    bridge = _bridge(manager)
    result = bridge.before_turn("audit", budget_tokens=512)
    assert result.source_scope == "faber.codex"
    assert result.selection.enforcement_mode == "per_layer_reader"
    assert '"state": "measured"' in result.context
    assert '"state": "blind"' in result.context
    assert '"reason": "owner instance"' in result.context
    assert result.selection.actual_tokens > 0


def test_layer_api_timeout_does_not_kill_the_turn(monkeypatch):
    """BL-3621: a dead status API renders as `unreachable`, it does not raise.

    The regression this pins: the read runs inside `before_turn`, so raising
    aborted the turn before the model was reached — a one-word message failed
    with "timed out" exactly like a long one.
    """
    def _boom(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("agent.symbiose_layer_provider.urlopen", _boom)
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    manager = _manager(provider)
    _settle(provider)
    bridge = _bridge(manager)

    result = bridge.before_turn("audit", budget_tokens=512)

    assert result.selection.enforcement_mode == "per_layer_reader"
    assert '"state": "unreachable"' in result.context
    assert "TimeoutError" in result.context


def test_sustained_outage_never_blocks_a_turn(monkeypatch):
    """The failure mode the blocking cold-read version actually had.

    When the very first read times out the cache stays empty, so a design that
    reads synchronously "only when cold" is synchronous on *every* turn for as
    long as the outage lasts.

    The turns deliberately span several refresh cycles (reviewer): if they all
    landed inside one in-flight window, a variant that blocks "only when cold
    AND nothing is in flight" would slip through — the pre-armed `_refreshing`
    flag would hide it.
    """
    def _slow_boom(request, timeout=None):
        time.sleep(0.3)
        raise TimeoutError("timed out")

    monkeypatch.setattr("agent.symbiose_layer_provider.urlopen", _slow_boom)
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    manager = _manager(provider)
    bridge = _bridge(manager)

    for _ in range(5):
        _settle(provider)  # no refresh in flight — the uncovered variant's window
        started = time.monotonic()
        bridge.before_turn("audit", budget_tokens=512)
        elapsed = time.monotonic() - started
        assert elapsed < 0.2, f"turn blocked {elapsed:.2f}s during an outage"


def test_thread_start_failure_neither_kills_the_turn_nor_freezes_refresh(monkeypatch):
    """Thread exhaustion is the saturated-host case this BL exists for.

    Two failures in one: the exception escaping `before_turn` is the original
    bug through a new door, and a `_refreshing` flag left set would freeze every
    future refresh for the life of the process — silently.
    """
    monkeypatch.setattr(
        "agent.symbiose_layer_provider.urlopen",
        lambda request, timeout=None: _Response(),
    )

    class _DeadThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr("agent.symbiose_layer_provider.threading.Thread", _DeadThread)

    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    manager = _manager(provider)
    bridge = _bridge(manager)

    result = bridge.before_turn("audit", budget_tokens=512)

    assert '"state": "unreachable"' in result.context
    with provider._lock:
        assert provider._refreshing is False, "refresh flag left set — provider frozen forever"
    assert "RuntimeError" in (provider._last_error or "")


def test_layer_read_is_cached_within_ttl(monkeypatch):
    calls: list[float | None] = []

    def _counted(request, timeout=None):
        calls.append(timeout)
        return _Response()

    monkeypatch.setattr("agent.symbiose_layer_provider.urlopen", _counted)
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    manager = _manager(provider)
    _settle(provider)
    bridge = _bridge(manager)

    for _ in range(5):
        bridge.before_turn("audit", budget_tokens=512)
        _settle(provider)

    assert len(calls) == 1, f"expected one network read across five turns, got {len(calls)}"


def test_expired_cache_refreshes_off_the_turn_path(monkeypatch):
    """A slow authoritative read costs staleness, not a stalled turn."""
    def _slow(request, timeout=None):
        time.sleep(1.0)
        return _Response()

    monkeypatch.setattr("agent.symbiose_layer_provider.urlopen", _slow)
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    provider._ttl = 0.0  # every turn finds the cache expired
    manager = _manager(provider)
    _settle(provider)
    bridge = _bridge(manager)

    started = time.monotonic()
    result = bridge.before_turn("audit", budget_tokens=512)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"turn blocked {elapsed:.2f}s on an expired-but-cached read"
    assert '"state": "measured"' in result.context


def test_stale_payload_is_served_and_labelled_stale(monkeypatch):
    state = {"fail": False}

    def _flaky(request, timeout=None):
        if state["fail"]:
            raise TimeoutError("timed out")
        return _Response()

    monkeypatch.setattr("agent.symbiose_layer_provider.urlopen", _flaky)
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    provider._ttl = 0.0
    manager = _manager(provider)
    _settle(provider)
    bridge = _bridge(manager)

    state["fail"] = True
    bridge.before_turn("audit", budget_tokens=512)  # kicks the failing refresh
    _settle(provider)
    result = bridge.before_turn("audit", budget_tokens=512)

    # The measured values survive the outage, but never pass as current.
    assert '"state": "measured"' in result.context
    assert '"stale": true' in result.context
    assert "TimeoutError" in result.context


def test_measured_rows_report_age_and_unmeasured_rows_do_not(monkeypatch):
    """Age is a property of a measurement — a row without one has no age to give."""
    monkeypatch.setattr(
        "agent.symbiose_layer_provider.urlopen",
        lambda request, timeout=None: _Response(),
    )
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    manager = _manager(provider)
    _settle(provider)
    bridge = _bridge(manager)

    result = bridge.before_turn("audit", budget_tokens=512)
    assert '"age_s"' in result.context

    cold = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    unread = cold.prefetch_layers(["episodisk"], "q")["episodisk"]
    assert '"age_s"' not in unread


def test_missing_layer_and_missing_payload_get_distinct_reasons(monkeypatch):
    """A layer absent from a good response is not the same fact as no response."""
    state = {"fail": False}

    def _flaky(request, timeout=None):
        if state["fail"]:
            raise TimeoutError("timed out")
        return _Response()

    monkeypatch.setattr("agent.symbiose_layer_provider.urlopen", _flaky)
    provider = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    provider.initialize("s1", user_id="morten")
    _settle(provider)

    absent = provider.prefetch_layers(["ikke_i_svaret"], "q")["ikke_i_svaret"]
    assert "absent from authoritative response" in absent

    # A failing refresh must not relabel an absent layer with the read's error:
    # that row never came from the read in the first place.
    provider._ttl = 0.0
    state["fail"] = True
    provider.prefetch_layers(["ikke_i_svaret"], "q")
    _settle(provider)
    still_absent = provider.prefetch_layers(["ikke_i_svaret"], "q")["ikke_i_svaret"]
    assert "absent from authoritative response" in still_absent
    assert "TimeoutError" not in still_absent

    cold = SymbioseLayerStatusProvider("http://symbiose.test/layers", "morten")
    unread = cold.prefetch_layers(["episodisk"], "q")["episodisk"]
    assert "no measurement yet" in unread
