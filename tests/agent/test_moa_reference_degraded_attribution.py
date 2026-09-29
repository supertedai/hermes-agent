"""A reference answered by the auxiliary fallback ladder must not be attributed to the dead slot.

The invariant bound here is general, not case-specific: **for every emitted ``moa.reference``
whose ``text`` is not a ``[failed:``/``[skipped:`` note, the attribution in the event must name
the route that ACTUALLY ran.** ``agent/moa_loop.py::_run_reference`` pre-resolved the label
(``label = _slot_label(slot)``) and called ``call_llm`` without ``route_info`` — the platform's
own channel for "which route was selected" (``agent/auxiliary_client.py::_record_route_info``,
also used by ``agent/context_compressor.py`` and ``agent/plugin_llm.py``) — so when the fallback
ladder substituted another lane, the substitute's answer was displayed, aggregated and priced as
the dead reference's.

Nothing here reaches a provider: ``call_llm`` is stubbed, and the stub emulates the ladder's own
contract (it records into ``route_info`` the lane it selected, exactly as ``auxiliary_client``
does) instead of asserting on a private detail of the caller.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

DEAD_PROVIDER, DEAD_MODEL = "xai-oauth", "grok-4.6"
SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL = "openai-api", "gpt-5.6-luna"
MARKER = f" [degraded → {SUBSTITUTE_PROVIDER}:{SUBSTITUTE_MODEL}]"


def _record(route_info, provider: str, model: str) -> None:
    """Emulate ``auxiliary_client``'s ``_record_route_info``.

    A caller that never asked for the channel has no dict to fill — which is exactly the defect
    under test: the ladder then has nowhere to publish the lane it selected, and the answer comes
    back with no attribution at all.
    """
    if isinstance(route_info, dict):
        route_info.update(provider=provider, model=model)


def _response(content: str, *, model: str, usage: Any = None):
    message = SimpleNamespace(content=content, tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(
        choices=[choice], model=model,
        usage=usage if usage is not None else SimpleNamespace(prompt_tokens=12, completion_tokens=4),
    )


@pytest.fixture
def moa_config(tmp_path, monkeypatch):
    """One preset with one configured (dead) reference slot and a live aggregator."""
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text(
        f"""
moa:
  default_preset: review
  presets:
    review:
      degraded_reference_policy: loud
      reference_models:
        - provider: {DEAD_PROVIDER}
          model: {DEAD_MODEL}
      aggregator:
        provider: openrouter
        model: anthropic/claude-opus-4.8
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    # Hermetic slot runtime: the dead slot's own endpoint/credentials (what pricing must NOT use
    # once another lane answered).
    monkeypatch.setattr(
        "agent.moa_loop._slot_runtime",
        lambda slot: {
            "provider": str(slot.get("provider") or ""), "model": str(slot.get("model") or ""),
            "base_url": "https://api.x.example/v1", "api_key": "dead-slot-key", "api_mode": "chat_completions",
        },
    )
    return home


def _install_ladder(monkeypatch, answer):
    """Stub ``call_llm``: ``answer(slot_model, route_info)`` emulates resolve + fallback ladder."""
    seen: list[dict] = []

    def fake_call_llm(**kwargs):
        if kwargs.get("task") != "moa_reference":
            return _response("acted", model="anthropic/claude-opus-4.8")
        seen.append(kwargs)
        return answer(kwargs.get("model"), kwargs.get("route_info"))

    monkeypatch.setattr("agent.moa_loop.call_llm", fake_call_llm)
    return seen


def _run_turn():
    """Run one MoA turn (fan-out only) and return ``(guidance, events, reference_outputs)``."""
    from agent.moa_loop import MoAChatCompletions

    events: list[tuple[str, dict]] = []
    facade = MoAChatCompletions(
        "review", reference_callback=lambda event, **kw: events.append((event, kw)),
    )
    prepared = facade.create(messages=[{"role": "user", "content": "clean the db"}], _moa_prepare_only=True)
    return prepared["guidance"], events, list(facade._ref_cache_outputs)


def _reference_events(events):
    return [kw for event, kw in events if event == "moa.reference"]


# ── 1. Substituted reference: the label names the lane that answered ────────────────────────────

def test_substituted_reference_is_attributed_to_the_lane_that_answered(moa_config, monkeypatch):
    """Primary 402s, the ladder's fallback answers: the emitted label, the aggregator guidance and
    the accounting must all name the substitute — and the answer must survive."""
    priced: list[dict] = []

    def answer(slot_model, route_info):
        assert slot_model == DEAD_MODEL, "the fan-out must still ask the CONFIGURED slot"
        # What auxiliary_client's ladder does to the caller-supplied channel before returning the
        # successful fallback response (_record_route_info, written right before the step that runs).
        _record(route_info, SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL)
        return _response("luna's advice", model=SUBSTITUTE_MODEL)

    _install_ladder(monkeypatch, answer)

    def fake_price(model_name, usage, *, provider=None, base_url=None, api_key=None):
        priced.append({"model": model_name, "provider": provider, "base_url": base_url, "api_key": api_key})
        return SimpleNamespace(amount_usd=None, status="unknown", source="none")

    with patch("agent.usage_pricing.estimate_usage_cost", fake_price):
        guidance, events, outputs = _run_turn()

    refs = _reference_events(events)
    assert len(refs) == 1
    # (a) the event label names the route that actually ran
    assert refs[0]["label"] == f"{DEAD_PROVIDER}:{DEAD_MODEL}{MARKER}"
    # the substitute's answer is still delivered — degraded is not failed
    assert refs[0]["text"] == "luna's advice"
    assert not refs[0]["text"].startswith("[failed:")

    # (b) aggregator guidance: reference header carries the marker...
    assert f"Reference 1 — {DEAD_PROVIDER}:{DEAD_MODEL}{MARKER}:" in guidance
    # ...and nothing claims the dead reference answered on its own (an unmarked header would end
    # the label with a bare colon right after the model id).
    assert f"{DEAD_PROVIDER}:{DEAD_MODEL}:" not in guidance
    # (c) loud policy names the slot that did NOT answer
    assert f"[Reference models unavailable: {DEAD_PROVIDER}:{DEAD_MODEL}]" in guidance

    # (d) accounting: configured pair kept, served pair recorded
    _label, _text, acct = outputs[0]
    assert (acct.provider, acct.model) == (DEAD_PROVIDER, DEAD_MODEL)
    assert (acct.served_provider, acct.served_model) == (SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL)
    # (e) priced on the serving route, never on the dead slot's endpoint/rate
    assert priced == [{"model": SUBSTITUTE_MODEL, "provider": SUBSTITUTE_PROVIDER, "base_url": None, "api_key": None}]


def test_substituted_accounting_is_visible_in_the_trace(moa_config, monkeypatch):
    """The serving lane reaches the persisted trace/metrics fields, not just the label."""
    def answer(_slot_model, route_info):
        _record(route_info, SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL)
        return _response("luna's advice", model=SUBSTITUTE_MODEL)

    _install_ladder(monkeypatch, answer)
    _guidance, _events, outputs = _run_turn()

    from agent.moa_trace import slot_metrics
    label, text, acct = outputs[0]
    metrics = slot_metrics(acct, label, output=text)
    assert metrics["served_provider"] == SUBSTITUTE_PROVIDER
    assert metrics["served_model"] == SUBSTITUTE_MODEL
    assert metrics["provider"] == DEAD_PROVIDER


# ── 2. Fallback also dead: unchanged [failed: …] shape, no marker ───────────────────────────────

def test_exhausted_ladder_keeps_the_failed_note_unmarked(moa_config, monkeypatch):
    """``route_info`` names the lane that was ATTEMPTED before the step ran; when that step (and
    every lane after it) fails, there is no serving route and the note keeps the configured label."""
    def answer(_slot_model, route_info):
        _record(route_info, SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL)
        raise RuntimeError("402 payment required on every lane")

    _install_ladder(monkeypatch, answer)
    guidance, events, outputs = _run_turn()

    refs = _reference_events(events)
    assert refs[0]["text"].startswith("[failed:")
    assert refs[0]["label"] == f"{DEAD_PROVIDER}:{DEAD_MODEL}"
    assert "[degraded" not in refs[0]["label"]
    assert "[degraded" not in guidance
    _label, _text, acct = outputs[0]
    assert (acct.served_provider, acct.served_model) == (None, None)
    assert f"[Reference models unavailable: {DEAD_PROVIDER}:{DEAD_MODEL}]" in guidance


# ── 3. No substitution: no marking at all ───────────────────────────────────────────────────────

def test_primary_route_recorded_as_configured_is_not_marked(moa_config, monkeypatch):
    """The primary path records the RESOLVED route too (``_prepare_aux_request``): recording a pair
    equal to the configured one is not a substitution."""
    def answer(_slot_model, route_info):
        _record(route_info, DEAD_PROVIDER, DEAD_MODEL)
        return _response("grok's advice", model=DEAD_MODEL)

    _install_ladder(monkeypatch, answer)
    guidance, events, outputs = _run_turn()

    assert _reference_events(events)[0]["label"] == f"{DEAD_PROVIDER}:{DEAD_MODEL}"
    assert "[degraded" not in guidance
    assert "unavailable" not in guidance
    _label, _text, acct = outputs[0]
    assert (acct.served_provider, acct.served_model) == (None, None)


def test_empty_route_info_means_ran_as_configured(moa_config, monkeypatch):
    """An untouched (empty) ``route_info`` is "ran as configured", never "unknown" — a caller that
    does not ask must not be marked as degraded."""
    _install_ladder(monkeypatch, lambda _slot_model, _route_info: _response("grok's advice", model=DEAD_MODEL))
    guidance, events, outputs = _run_turn()

    assert _reference_events(events)[0]["label"] == f"{DEAD_PROVIDER}:{DEAD_MODEL}"
    assert "[degraded" not in guidance
    _label, _text, acct = outputs[0]
    assert (acct.served_provider, acct.served_model) == (None, None)


# ── 4. Two hops: the SECOND lane is the one attributed ──────────────────────────────────────────

def test_second_hop_is_attributed_when_the_first_candidate_is_quarantined(moa_config, monkeypatch):
    """Hop 1 is quarantined (returns nothing, so the walk records hop 2 before it runs) and hop 2
    answers: the label must name hop 2, the lane that produced the answer."""
    second = "anthropic:claude-opus-5"

    def answer(_slot_model, route_info):
        _record(route_info, SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL)   # hop 1: quarantined
        _record(route_info, "anthropic", "claude-opus-5")            # hop 2: answered
        return _response("claude's advice", model="claude-opus-5")

    _install_ladder(monkeypatch, answer)
    guidance, events, _outputs = _run_turn()

    assert _reference_events(events)[0]["label"] == f"{DEAD_PROVIDER}:{DEAD_MODEL} [degraded → {second}]"
    assert f"[degraded → {second}]" in guidance


def test_ladder_records_the_answering_lane_in_route_info(monkeypatch):
    """The premise of case 4 lives in ``auxiliary_client``, not in this change: its ladder writes
    the lane BEFORE the step runs, so after quarantine-then-success ``route_info`` must hold the
    lane that answered. Driven through the REAL generator (``_ladder_provider_fallback``), not an
    emulation — a private re-implementation here would only assert itself."""
    from agent import auxiliary_client as aux

    class _Http402(Exception):
        status_code = 402

    route_info: dict[str, str] = {}
    route = aux._LadderRoute(
        client=SimpleNamespace(base_url="https://api.x.example/v1"), task="moa_reference", tag="",
        async_mode=False, base_info="https://api.x.example/v1", resolved_provider=DEAD_PROVIDER,
        resolved_model=DEAD_MODEL, resolved_base_url=None, resolved_api_key=None, resolved_api_mode=None,
        final_model=DEAD_MODEL, main_runtime=None, route_info=route_info, timeout=30.0,
    )
    monkeypatch.setattr(aux, "_mark_provider_unhealthy", lambda *a, **k: None)
    monkeypatch.setattr(
        aux, "_try_configured_fallback_chain",
        lambda *a, **k: (SimpleNamespace(base_url="https://api.openai.example/v1"), SUBSTITUTE_MODEL,
                         f"fallback_chain[0]({SUBSTITUTE_PROVIDER})"),
    )
    monkeypatch.setattr(
        aux, "_next_fallback_after_quarantine",
        lambda *a, **k: (SimpleNamespace(base_url="https://api.anthropic.example"), "claude-opus-5",
                         "fallback_providers[0](anthropic)"),
    )

    answered = SimpleNamespace(model="claude-opus-5", choices=[])
    performed: list[tuple] = []

    def perform(step):
        performed.append(step.args)
        return None if len(performed) == 1 else answered   # hop 1 quarantined, hop 2 answers

    result = aux._drive_ladder(aux._ladder_provider_fallback(_Http402("402 payment required"), route), perform)

    assert len(performed) == 2
    assert result is answered
    assert route_info == {"provider": "anthropic", "model": "claude-opus-5"}, (
        "route_info must name the lane that ANSWERED, not the quarantined first candidate"
    )


# ── 5. The cache replays what happened; a fresh run recomputes it ───────────────────────────────

def test_cache_hit_keeps_the_label_and_a_fresh_run_does_not_inherit_it(moa_config, monkeypatch):
    """A cache HIT replays the turn's own label (still true), and a later fan-out against a healthy
    primary must not inherit the earlier ``[degraded …]`` marker."""
    calls: list[str] = []
    state = {"substituted": True}

    def answer(_slot_model, route_info):
        calls.append("ref")
        if state["substituted"]:
            _record(route_info, SUBSTITUTE_PROVIDER, SUBSTITUTE_MODEL)
            return _response("luna's advice", model=SUBSTITUTE_MODEL)
        return _response("grok's advice", model=DEAD_MODEL)

    _install_ladder(monkeypatch, answer)

    from agent.moa_loop import MoAChatCompletions
    events: list[tuple[str, dict]] = []
    facade = MoAChatCompletions("review", reference_callback=lambda event, **kw: events.append((event, kw)))
    messages = [{"role": "user", "content": "clean the db"}]

    first = facade.create(messages=messages, _moa_prepare_only=True)
    assert f"{DEAD_PROVIDER}:{DEAD_MODEL}{MARKER}" in first["guidance"]
    assert len(calls) == 1

    # Same user turn (same cache signature): HIT — no new call, same (still true) label, and the
    # fan-out does not re-emit the reference event.
    hit = facade.create(messages=messages, _moa_prepare_only=True)
    assert len(calls) == 1, "a cache HIT must not re-run the advisors"
    assert hit["guidance"] == first["guidance"]
    assert len(_reference_events(events)) == 1

    # A NEW user turn whose primary now answers: the marker must not stick to the healthy run.
    state["substituted"] = False
    fresh = facade.create(messages=[*messages, {"role": "assistant", "content": "ok"},
                                    {"role": "user", "content": "try again"}], _moa_prepare_only=True)
    assert len(calls) == 2
    assert "[degraded" not in fresh["guidance"]
    assert re.search(rf"{re.escape(DEAD_PROVIDER)}:{re.escape(DEAD_MODEL)}:", fresh["guidance"])
