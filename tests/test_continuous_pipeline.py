from __future__ import annotations

import json
import os
import pytest
from pathlib import Path

from agent.continuous_pipeline import (
    ActionProposal,
    ActionGate,
    ApprovalDecision,
    CANONICAL_MEMORY_LAYER_IDS,
    CostAwareModelRouter,
    ContinuousPipeline,
    FileMemoryProvider,
    GoalProposal,
    JsonStateStore,
    LoopOutcome,
    MemorySnapshot,
    MemoryLayerSpec,
    MemoryManagerBridge,
    MemoryScheduler,
    ModelRouting,
    Observation,
    Reasoning,
    DEFAULT_OPTIMIZATION_LOOPS,
    LEGACY_CMC_SMM_LAYER_IDS,
    LEGACY_TO_CANONICAL_MEMORY_LAYERS,
    validate_legacy_memory_projection,
    estimate_memory_tokens,
    trim_memory_to_budget,
    LearningMeasurement,
    LearningMeasurementStore,
    ExecutionLedger,
    runtime_open,
)


class Memory:
    def snapshot(self, layers) -> MemorySnapshot:
        return MemorySnapshot(tuple(layers), tuple(layers), ())


class Adapter:
    def __init__(self, confidence: float = 0.9, needs_more_evidence: bool = False, action: bool = True):
        self.confidence = confidence
        self.needs_more_evidence = needs_more_evidence
        self.action = action
        self.executed = False

    def sense(self, memory: MemorySnapshot) -> Observation:
        return Observation(facts={"health": "ok"}, sources=("test",), memory=memory)

    def reason(self, observation: Observation, routing: ModelRouting) -> Reasoning:
        return Reasoning(
            conclusion="continue",
            confidence=self.confidence,
            needs_more_evidence=self.needs_more_evidence,
        )

    def propose_goals(self, observation: Observation, reasoning: Reasoning):
        return []

    def propose_action(self, observation: Observation, reasoning: Reasoning):
        return ActionProposal("safe reversible action") if self.action else None

    def execute(self, action: ActionProposal, routing: ModelRouting):
        self.executed = True
        return {"status": "executed", "builder": routing.builder}

    def learn(self, result):
        return {"outcome": result.outcome.value}


def test_low_confidence_is_proposal_and_does_not_execute():
    adapter = Adapter(confidence=0.94)
    pipeline = ContinuousPipeline(adapter, Memory(), require_live_router=False)
    result = pipeline.tick()
    assert result.outcome is LoopOutcome.PROPOSE
    assert not adapter.executed


def test_act_requires_confidence_and_explicit_approval(tmp_path: Path):
    adapter = Adapter(confidence=0.99)
    adapter.action = False
    adapter.propose_action = lambda observation, reasoning: ActionProposal("safe", requires_morten=False, idempotency_key="act-1")
    pipeline = ContinuousPipeline(
        adapter,
        Memory(),
        router=CostAwareModelRouter(resolver=lambda role: "live-" + role),
        execution_ledger=ExecutionLedger(tmp_path / "execution.json"),
        approval=lambda action: True,
    )
    result = pipeline.tick()
    assert result.outcome is LoopOutcome.ACT
    assert adapter.executed


def test_action_gate_rejects_bare_approval_for_morten_or_reviewer_actions():
    assert not ActionGate.allows(ActionProposal("gated"), True)
    assert not ActionGate.allows(ActionProposal("review", requires_landing_gate=True), True)
    assert not ActionGate.allows(ActionProposal("unknown", risk="UNCLASSIFIED", requires_morten=False), True)
    assert not ActionGate.allows(ActionProposal("code", risk="low", mutates_code=True, requires_morten=False), True)
    assert not ActionGate.allows(
        ActionProposal("high", risk="high", requires_morten=False),
        ApprovalDecision(operator_approved=True),
    )
    assert ActionGate.allows(
        ActionProposal("gated"),
        ApprovalDecision(operator_approved=True, morten_approved=True),
    )


def test_uncertainty_blocks_action_even_with_approval():
    adapter = Adapter(confidence=0.99, needs_more_evidence=True)
    pipeline = ContinuousPipeline(adapter, Memory(), require_live_router=False, approval=lambda action: True)
    result = pipeline.tick()
    assert result.outcome is LoopOutcome.PROPOSE
    assert not adapter.executed


def test_memory_registry_reports_missing_layers(tmp_path: Path):
    registry = tmp_path / "memory.json"
    registry.write_text(json.dumps({"episodic": {"provenance": "test"}}), encoding="utf-8")
    snapshot = FileMemoryProvider(registry).snapshot(("episodic", "self_model", "world_model"))
    assert snapshot.available == ("episodic",)
    assert snapshot.missing == ("self_model", "world_model")
    assert snapshot.provenance["episodic"] == "test"


def test_state_store_is_readable_and_bounded(tmp_path: Path):
    adapter = Adapter(action=False)
    state_path = tmp_path / "state.json"
    pipeline = ContinuousPipeline(adapter, Memory(), state=JsonStateStore(state_path), require_live_router=False)
    pipeline.tick()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["outcome"] == "OBSERVE"


def test_runtime_wake_binds_code_to_faber_and_never_allows_action():
    wake = runtime_open(now=lambda: "fixed-time")
    assert wake.owner == "code"
    assert wake.steward == "faber"
    assert wake.opened_at == "fixed-time"
    assert wake.projection == "code"
    assert wake.action_allowed is False
    assert wake.active_loops == tuple(loop.loop_id for loop in DEFAULT_OPTIMIZATION_LOOPS)
    assert all(loop.owner == "faber" for loop in DEFAULT_OPTIMIZATION_LOOPS)


def test_memory_scheduler_keeps_required_layers_and_respects_optional_budget():
    scheduler = MemoryScheduler(
        (
            MemoryLayerSpec("governance", "graph", priority=10, max_tokens=400, required_phases=("reason",)),
            MemoryLayerSpec("episodic", "graph", priority=3, max_tokens=400),
            MemoryLayerSpec("semantic", "qdrant", priority=4, max_tokens=400),
        )
    )
    selection = scheduler.select(phase="reason", budget_tokens=800, relevance={"semantic": 1.0})
    assert selection.selected == ("governance", "semantic")
    assert selection.estimated_tokens == 800
    assert selection.excluded == ("episodic",)


def test_memory_scheduler_reports_required_budget_overflow_without_dropping_context():
    scheduler = MemoryScheduler(
        (MemoryLayerSpec("governance", "graph", priority=10, max_tokens=900, required_phases=("reason",)),)
    )
    selection = scheduler.select(phase="reason", budget_tokens=400)
    assert selection.selected == ("governance",)
    assert selection.budget_exceeded is True


def test_canonical_memory_registry_is_exactly_twenty_layers():
    specs = tuple(MemoryLayerSpec(layer_id, "canonical") for layer_id in CANONICAL_MEMORY_LAYER_IDS)
    MemoryScheduler(specs, require_canonical=True)
    with pytest.raises(ValueError):
        MemoryScheduler(specs[:-1], require_canonical=True)


def test_pipeline_records_scheduler_selection():
    adapter = Adapter(action=False)
    scheduler = MemoryScheduler((MemoryLayerSpec("episodic", "canonical", max_tokens=100),))
    result = ContinuousPipeline(
        adapter,
        Memory(),
        memory_scheduler=scheduler,
        memory_token_budget=100,
        require_live_router=False,
    ).tick()
    assert result.memory_selection is not None
    assert result.memory_selection.selected == ("episodic",)


def test_model_router_avoids_llm_for_retrieval_and_resolves_quality_route_live():
    router = CostAwareModelRouter(resolver=lambda role: {
        "builder": "live-builder-id",
        "reviewer": "live-reviewer-id",
    }[role])
    assert router.route("retrieve").model_ref is None
    review = router.route("review", complexity="high")
    assert review.max_output_tokens == 4096
    assert review.quality_floor == 0.95
    assert review.model_ref == "live-reviewer-id"
    assert router.telemetry[-1].resolved is True
    assert router.telemetry[-1].resolver_latency_ms >= 0


def test_model_router_persists_measured_outcome_and_blocks_unknown_task(tmp_path):
    router = CostAwareModelRouter(
        resolver=lambda role: "live-" + role,
        telemetry_path=tmp_path / "routing.json",
    )
    router.route("review")
    router.record_outcome(task="review", actual_quality=0.97, execution_latency_ms=123.0, estimated_cost=0.42)
    data = json.loads((tmp_path / "routing.json").read_text())
    assert data[-1]["actual_quality"] == pytest.approx(0.97)
    assert data[-1]["execution_latency_ms"] == pytest.approx(123.0)
    assert data[-1]["estimated_cost"] == pytest.approx(0.42)
    with pytest.raises(RuntimeError, match="no governed model route"):
        router.route("unknown-task")


def test_learning_measurement_requires_validation_for_improvement():
    unvalidated = LearningMeasurement("accuracy", 0.5, 0.7, 0.8, validated=False, skill_or_workflow="wf1")

    assert unvalidated.delta == pytest.approx(0.2)
    assert not unvalidated.improved
    assert unvalidated.to_event()["improved"] is False

    validated = LearningMeasurement("accuracy", 0.5, 0.7, 0.95, validated=True, skill_or_workflow="wf1")
    assert validated.improved
    assert validated.to_event()["delta"] == pytest.approx(0.2)


def test_learning_measurement_store_requires_validation_for_claimed_improvement(tmp_path):
    store = LearningMeasurementStore(tmp_path / "learning.json")
    event = store.record(LearningMeasurement("accuracy", 0.5, 0.7, 0.95, validated=True, skill_or_workflow="wf1"))
    assert event["improved"] is True
    assert json.loads((tmp_path / "learning.json").read_text())[0]["validated"] is True
    with pytest.raises(ValueError, match="skill_or_workflow"):
        store.record(LearningMeasurement("accuracy", 0.5, 0.7, 0.95, validated=True))




def test_pipeline_binds_live_model_router_to_tick_routing():
    adapter = Adapter(action=False)
    router = CostAwareModelRouter(resolver=lambda role: {
        "builder": "builder-live",
        "reviewer": "reviewer-live",
    }[role])
    result = ContinuousPipeline(adapter, Memory(), router=router).tick()
    assert result.model_routing.builder == "builder-live"
    assert result.model_routing.designer_reviewer == "reviewer-live"
    assert len(router.telemetry) == 2


def test_model_router_exposes_sol_luna_120b_and_671b_roles():
    router = CostAwareModelRouter(resolver=lambda role: {
        "designer": "sol-live",
        "reviewer": "sol-live",
        "builder": "luna-live",
        "builder_120b": "120b-live",
        "builder_671b": "671b-live",
    }[role])
    assert router.route("design").model_ref == "sol-live"
    assert router.route("review").model_ref == "sol-live"
    assert router.route("build").model_ref == "luna-live"
    assert router.route("build_120b").model_ref == "120b-live"
    assert router.route("build_671b").model_ref == "671b-live"


def test_default_role_resolver_reads_authoritative_hermes_config_and_env(monkeypatch):
    for key in ("HERMES_LUNA_MODEL", "HERMES_BUILDER_MODEL", "HERMES_120B_MODEL", "HERMES_671B_MODEL"):
        monkeypatch.delenv(key, raising=False)
    # Tests deliberately run with an isolated HERMES_HOME. Seed the canonical
    # config there instead of reaching through Path.home() into the operator's
    # live profile.
    hermes_home = Path(os.environ["HERMES_HOME"])
    (hermes_home / "config.yaml").write_text(
        "model:\n  default: gpt-5.6-luna\n  provider: openai-api\n",
        encoding="utf-8",
    )
    from agent.continuous_pipeline import default_live_model_resolver
    assert default_live_model_resolver("builder") == "gpt-5.6-luna"
    # The isolated config has no 120B route; its resolver must not invent a
    # hard-coded model ID. An explicitly configured route is accepted.
    monkeypatch.setenv("HERMES_120B_MODEL", "gpt-oss-120b")
    assert default_live_model_resolver("builder_120b") == "gpt-oss-120b"


def test_goal_sink_emits_proposal_without_act():
    class GoalAdapter(Adapter):
        def propose_goals(self, observation, reasoning):
            return [GoalProposal("TUI job", "measured", goal_id="g1", cad_ref="CAD-M", adr_ref="ADR-042", bl_ref="BL-3596", rollback="revert", job_spec={"schedule": "0 9 * * *"})]

    emitted = []
    result = ContinuousPipeline(
        GoalAdapter(action=False, confidence=0.99),
        Memory(),
        require_live_router=False,
        goal_sink=lambda goal: emitted.append(goal.goal_id) or {"status": "pending"},
    ).tick()
    assert emitted == ["g1"]
    assert result.goals[0].trace_id == result.tick_id
    assert result.proposal_results == ({"status": "pending"},)
    assert result.outcome is LoopOutcome.OBSERVE


def test_model_router_fails_closed_without_live_resolver_for_quality_route():
    with pytest.raises(RuntimeError, match="dynamic model resolver"):

        CostAwareModelRouter().route("review")


def test_memory_manager_bridge_preserves_existing_hook_lifecycle():
    class Manager:
        def __init__(self):
            self.calls = []
        def prefetch_all(self, query, *, session_id="", strict=False):
            self.calls.append(("prefetch", query, session_id))
            return "canonical-context"
        def sync_all(self, user, assistant, *, session_id="", messages=None):
            self.calls.append(("sync", user, assistant, session_id))
        def queue_prefetch_all(self, query, *, session_id=""):
            self.calls.append(("queue", query, session_id))
        def on_pre_compress(self, messages):
            self.calls.append(("compress", messages))
            return "preserve"
        def on_session_end(self, messages):
            self.calls.append(("end", messages))

    manager = Manager()
    bridge = MemoryManagerBridge(
        manager,
        MemoryScheduler((MemoryLayerSpec("episodic", "canonical", max_tokens=100),)),
        source_scope="faber.codex",
    )
    result = bridge.before_turn("query", session_id="s1", budget_tokens=100)
    bridge.after_turn("u", "a", session_id="s1")
    assert result.context == "canonical-context"
    assert result.source_scope == "faber.codex"
    assert result.selection.selected == ("episodic",)
    assert bridge.before_compress([]) == "preserve"
    bridge.session_end([])
    assert [call[0] for call in manager.calls] == ["prefetch", "sync", "queue", "compress", "end"]


def test_legacy_nine_layer_projection_covers_canonical_registry():
    validate_legacy_memory_projection()
    assert tuple(LEGACY_TO_CANONICAL_MEMORY_LAYERS) == LEGACY_CMC_SMM_LAYER_IDS
    projected = {
        layer
        for layers in LEGACY_TO_CANONICAL_MEMORY_LAYERS.values()
        for layer in layers
    }
    assert projected == set(CANONICAL_MEMORY_LAYER_IDS)


def test_missing_selected_memory_blocks_act():
    class MissingMemory:
        def snapshot(self, layers):
            return MemorySnapshot(tuple(layers), (), tuple(layers))

    adapter = Adapter(confidence=0.99)
    adapter.action = True
    adapter.propose_action = lambda observation, reasoning: ActionProposal(
        "safe", requires_morten=False, idempotency_key="missing-memory"
    )
    router = CostAwareModelRouter(resolver=lambda role: "live-" + role)
    result = ContinuousPipeline(
        adapter,
        MissingMemory(),
        memory_layers=("governance",),
        router=router,
        execution_ledger=ExecutionLedger(Path("/tmp/faber-test-execution.json")),
        approval=lambda action: True,
        require_live_router=True,
    ).tick()
    assert result.outcome is LoopOutcome.PROPOSE
    assert not adapter.executed


def test_memory_manager_bridge_strict_mode_blocks_aggregate_fallback():
    class Manager:
        def prefetch_all(self, query, *, session_id="", strict=False):
            return "aggregate"

    bridge = MemoryManagerBridge(
        Manager(),
        MemoryScheduler((MemoryLayerSpec("governance", "canonical", max_tokens=100),)),
        strict=True,
    )
    with pytest.raises(RuntimeError, match="per-layer reader required"):
        bridge.before_turn("q", phase="sense")


def test_execution_ledger_is_crash_safe_and_idempotent(tmp_path):
    ledger = ExecutionLedger(tmp_path / "execution.json")

    assert ledger.claim("run-1")
    assert ledger.status("run-1") == "started"
    assert not ledger.claim("run-1")
    ledger.complete("run-1")
    assert ledger.status("run-1") == "completed"
    assert not ledger.claim("run-1")
    with pytest.raises(ValueError):
        ledger.claim("")
    (tmp_path / "corrupt.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unreadable"):
        ExecutionLedger(tmp_path / "corrupt.json").claim("retry")


def test_memory_manager_bridge_enforces_actual_aggregate_output_budget():
    class Manager:
        def prefetch_all(self, query, *, session_id="", strict=False):
            return "x" * 1000

    bridge = MemoryManagerBridge(
        Manager(),
        MemoryScheduler((MemoryLayerSpec("episodisk", "canonical", max_tokens=100),)),
    )
    result = bridge.before_turn("q", budget_tokens=10)
    assert estimate_memory_tokens(result.context) <= 12
    assert result.selection.enforcement_mode == "aggregate_output_fallback"
    assert result.selection.actual_tokens == estimate_memory_tokens(result.context)
    assert "truncated" in result.context


def test_memory_manager_bridge_uses_per_layer_reader_when_available():
    class Manager:
        def prefetch_all(self, query, *, session_id="", strict=False):
            raise AssertionError("per-layer reader must be preferred")

        def prefetch_layers(self, layers, query, *, session_id=""):
            return {layer: layer * 100 for layer in layers}

    bridge = MemoryManagerBridge(
        Manager(),
        MemoryScheduler((MemoryLayerSpec("episodisk", "canonical", max_tokens=20),)),
    )
    result = bridge.before_turn("q", budget_tokens=20)
    assert result.selection.enforcement_mode == "per_layer_reader"
    assert estimate_memory_tokens(result.context) <= 20


# ── BL-3643/ADR-044 D3: strict er kapabilitets-avledet, aldri en tur som dør ──────────
# Rotårsak 2026-08-04: strict=True var begrunnet med fallback_rate=0.0 målt mot en TOM
# MemoryManager (triviell suksess). Live sto Mortens opus-provider uten prefetch_layers,
# og hver gateway-tur døde på raisen. Disse testene fryser begge halvdeler av fiksen.

def _opus_shaped_provider():
    """Samme form som ~/.hermes/plugins/opus: ingen prefetch_layers-override."""
    from agent.memory_provider import MemoryProvider

    class OpusShaped(MemoryProvider):
        @property
        def name(self):
            return "opus-shaped"

        def is_available(self):
            return True

        def initialize(self, session_id, **kwargs):
            return None

        def prefetch(self, query, *, session_id=""):
            return ""

        def get_tool_schemas(self):
            return []

    return OpusShaped()


def test_supports_layer_reads_false_for_provider_without_override():
    from agent.memory_manager import MemoryManager

    mm = MemoryManager()
    mm.add_provider(_opus_shaped_provider())
    assert mm.supports_layer_reads() is False


def test_supports_layer_reads_false_for_empty_manager():
    from agent.memory_manager import MemoryManager

    assert MemoryManager().supports_layer_reads() is False


def test_supports_layer_reads_true_for_overriding_provider():
    from agent.memory_manager import MemoryManager
    from agent.symbiose_layer_provider import SymbioseLayerStatusProvider

    mm = MemoryManager()
    mm.add_provider(SymbioseLayerStatusProvider())
    assert mm.supports_layer_reads() is True


def test_empty_manager_prefetch_layers_is_capability_absence_not_success():
    """Tom manager skal IKKE kunne minte fallback_rate=0.0 (den vakuøse målingen)."""
    from agent.memory_manager import MemoryManager

    assert MemoryManager().prefetch_layers(["episodisk"], "q") is None


def test_capability_derived_strict_survives_the_turn_with_opus_shaped_provider():
    """ADR-044 D3: med en provider uten per-lag-flate faller turen ærlig tilbake — den dør ikke."""
    from agent.memory_manager import MemoryManager

    mm = MemoryManager()
    mm.add_provider(_opus_shaped_provider())
    bridge = MemoryManagerBridge(
        mm,
        MemoryScheduler((MemoryLayerSpec("episodisk", "canonical", max_tokens=100),)),
        strict=mm.supports_layer_reads(),
    )
    result = bridge.before_turn("hei", phase="sense")
    assert result.selection.enforcement_mode == "aggregate_output_fallback"
    assert bridge.aggregate_fallback_calls == 1
