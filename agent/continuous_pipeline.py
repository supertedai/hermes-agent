"""Continuous Hermes agent pipeline.

This module is deliberately model-agnostic: Hermes owns the loop and gates;
model adapters supply sensing, reasoning, planning, building, and review.
The default policy is fail-closed: a tick can observe, propose, or act only
when an explicit approval is present.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


class LoopOutcome(str, Enum):
    OBSERVE = "OBSERVE"
    PROPOSE = "PROPOSE"
    ACT = "ACT"


CODE_OWNER = "code"
FABER_STEWARD = "faber"


@dataclass(frozen=True)
class OptimizationLoop:
    """One measurable optimization loop owned by Code/faber."""

    loop_id: str
    phase: str
    interval_minutes: int
    mode: str = "OBSERVE/PROPOSE"
    requires_approval: bool = True
    owner: str = FABER_STEWARD


@dataclass(frozen=True)
class MemoryLayerSpec:
    """Selection metadata for an existing canonical memory reader.

    This is not a storage definition. The actual reader/writer/scope remains
    owned by Hermes/Symbiose's existing memory-layer implementation.
    """

    layer_id: str
    source: str
    priority: int = 1
    max_tokens: int = 256
    freshness_minutes: int = 120
    required_phases: tuple[str, ...] = ()
    retrieval_cost: float = 1.0


CANONICAL_MEMORY_LAYER_IDS: tuple[str, ...] = (
    "episodisk",
    "semantisk",
    "erfaring",
    "kausalt",
    "epistemisk",
    "temporalt",
    "proseduralt",
    "prospektivt",
    "autobiografisk",
    "sosialt",
    "assosiativt",
    "salient",
    "governance",
    "kontrafaktisk",
    "konsolidering",
    "metaminne",
    "reflektivt",
    "utility",
    "prediksjon",
    "affordance",
)

# Legacy 9-layer architecture from SOURCE:
# /Users/morpheus/AGI/tools/optimal_memory_system.py (read 2026-08-04).
# This is a compatibility projection, not a second registry and not a claim
# that one legacy component is equivalent to one canonical layer. A legacy
# component may project into several canonical layers, and every canonical
# layer must have an explicit projection before a scheduler can accept the
# legacy taxonomy.
LEGACY_CMC_SMM_LAYER_IDS: tuple[str, ...] = (
    "CMC",
    "SMM",
    "Neo4j",
    "DDE",
    "AME",
    "MLC",
    "MIR",
    "MCA",
    "MCE",
)

LEGACY_TO_CANONICAL_MEMORY_LAYERS: dict[str, tuple[str, ...]] = {
    "CMC": ("semantisk", "episodisk", "autobiografisk", "sosialt", "governance"),
    "SMM": ("semantisk", "assosiativt", "salient", "temporalt", "erfaring"),
    "Neo4j": ("kausalt", "prediksjon", "utility"),
    "DDE": ("epistemisk", "affordance"),
    "AME": ("governance", "kontrafaktisk", "prospektivt"),
    "MLC": ("metaminne", "reflektivt", "proseduralt"),
    "MIR": ("salient", "kontrafaktisk", "epistemisk"),
    "MCA": ("epistemisk", "governance", "utility"),
    "MCE": ("konsolidering", "temporalt", "proseduralt"),
}


def validate_legacy_memory_projection() -> None:
    """Reject incomplete/ambiguous legacy-to-canonical compatibility maps."""
    if tuple(LEGACY_TO_CANONICAL_MEMORY_LAYERS) != LEGACY_CMC_SMM_LAYER_IDS:
        raise ValueError("legacy memory projection must define all nine SOURCE layers exactly once")
    projected = {
        layer
        for layers in LEGACY_TO_CANONICAL_MEMORY_LAYERS.values()
        for layer in layers
    }
    missing = sorted(set(CANONICAL_MEMORY_LAYER_IDS) - projected)
    unknown = sorted(projected - set(CANONICAL_MEMORY_LAYER_IDS))
    if missing or unknown:
        raise ValueError(
            "legacy memory projection must cover canonical registry; "
            f"missing={missing}, unknown={unknown}"
        )


validate_legacy_memory_projection()


def validate_canonical_memory_registry(specs: Sequence[MemoryLayerSpec]) -> None:
    """Require the authoritative 20-layer registry; reject ad-hoc taxonomies."""
    actual = tuple(spec.layer_id for spec in specs)
    if set(actual) != set(CANONICAL_MEMORY_LAYER_IDS) or len(actual) != 20:
        missing = sorted(set(CANONICAL_MEMORY_LAYER_IDS) - set(actual))
        extra = sorted(set(actual) - set(CANONICAL_MEMORY_LAYER_IDS))
        raise ValueError(f"canonical memory registry must contain exactly 20 layers; missing={missing}, extra={extra}")


@dataclass(frozen=True)
class MemorySelection:
    selected: tuple[str, ...]
    excluded: tuple[str, ...]
    estimated_tokens: int
    budget_tokens: int
    budget_exceeded: bool = False
    actual_tokens: int = 0
    enforcement_mode: str = "selection_only"


def estimate_memory_tokens(text: str) -> int:
    """Conservative deterministic estimate used for provider-output gating."""
    return max(0, (len(text) + 3) // 4)


def trim_memory_to_budget(text: str, budget_tokens: int) -> str:
    """Trim provider context to a hard deterministic token-equivalent budget."""
    if budget_tokens < 0:
        raise ValueError("budget_tokens must be non-negative")
    max_chars = budget_tokens * 4
    if len(text) <= max_chars:
        return text
    marker = "\n[Memory context truncated.]"
    body_chars = max(0, max_chars - len(marker))
    return (text[:body_chars].rstrip() + marker)[:max_chars]


class MemoryScheduler:
    """Token/freshness scheduler over canonical memory readers.

    It selects *which existing layers to ask*, not where memories are stored.
    That distinction preserves ADR-038 D3/D4 and avoids a second memory stack.
    """

    def __init__(self, specs: Sequence[MemoryLayerSpec], *, require_canonical: bool = False):
        self.specs = tuple(specs)
        ids = [spec.layer_id for spec in self.specs]
        if len(ids) != len(set(ids)):
            raise ValueError("memory layer IDs must be unique")
        if require_canonical:
            validate_canonical_memory_registry(self.specs)

    def select(
        self,
        *,
        phase: str,
        budget_tokens: int,
        age_minutes: Mapping[str, float] | None = None,
        relevance: Mapping[str, float] | None = None,
    ) -> MemorySelection:
        if budget_tokens < 0:
            raise ValueError("budget_tokens must be non-negative")
        age_minutes = age_minutes or {}
        relevance = relevance or {}
        mandatory = [s for s in self.specs if phase in s.required_phases]
        optional = [s for s in self.specs if s not in mandatory]

        def score(spec: MemoryLayerSpec) -> float:
            age = max(0.0, float(age_minutes.get(spec.layer_id, 0.0)))
            freshness = max(0.0, 1.0 - age / max(1, spec.freshness_minutes))
            rel = max(0.0, min(1.0, float(relevance.get(spec.layer_id, 0.0))))
            return spec.priority * 10.0 + rel * 5.0 + freshness * 3.0 - spec.retrieval_cost

        chosen: list[MemoryLayerSpec] = []
        used = 0
        # Required layers are selected first. If they exceed budget, the
        # selection reports it instead of silently dropping governance context.
        for spec in sorted(mandatory, key=score, reverse=True):
            chosen.append(spec)
            used += spec.max_tokens
        for spec in sorted(optional, key=score, reverse=True):
            if used + spec.max_tokens <= budget_tokens:
                chosen.append(spec)
                used += spec.max_tokens
        selected = tuple(spec.layer_id for spec in chosen)
        excluded = tuple(spec.layer_id for spec in self.specs if spec.layer_id not in selected)
        return MemorySelection(selected, excluded, used, budget_tokens, used > budget_tokens)


@dataclass(frozen=True)
class MemoryHookResult:
    selection: MemorySelection
    context: str = ""
    # Label carried from the bridge: which scoped consumer this context was
    # assembled for (e.g. "faber.codex"). Empty for unscoped callers.
    source_scope: str = ""


class MemoryManagerBridge:
    """Adapter around Hermes' existing MemoryManager lifecycle.

    The bridge adds selection/budget observability without replacing provider
    storage, scopes, or hook semantics. Provider-specific retrieval remains
    authoritative until the canonical layer registry exposes per-layer reads.
    """

    def __init__(
        self,
        manager: Any,
        scheduler: MemoryScheduler,
        *,
        strict: bool = False,
        source_scope: str = "",
    ):
        self.manager = manager
        self.scheduler = scheduler
        # strict: this bridge feeds a scoped consumer (e.g. Faber), and the
        # merged prefetch_all fallback would smuggle unscoped provider
        # context across that boundary — deliver nothing instead, labelled
        # honestly via enforcement_mode. source_scope rides on every
        # MemoryHookResult so downstream provenance can name the consumer.
        self.strict = strict
        self.source_scope = source_scope

    def before_turn(
        self,
        query: str,
        *,
        session_id: str = "",
        phase: str = "sense",
        budget_tokens: int = 1800,
    ) -> MemoryHookResult:
        selection = self.scheduler.select(phase=phase, budget_tokens=budget_tokens)
        # Existing MemoryManager exposes a merged provider context. Prefer an
        # explicit per-layer reader when available; otherwise enforce the
        # budget at the actual merged provider-output boundary and label the
        # fallback honestly.
        actual_tokens = 0
        mode = "aggregate_output_fallback"
        layer_prefetch = getattr(self.manager, "prefetch_layers", None)
        context = ""
        if callable(layer_prefetch):
            layered = layer_prefetch(selection.selected, query, session_id=session_id)
            if isinstance(layered, Mapping):
                chunks: list[str] = []
                for layer in selection.selected:
                    chunk = str(layered.get(layer, ""))
                    chunks.append(trim_memory_to_budget(chunk, next(
                        (spec.max_tokens for spec in self.scheduler.specs if spec.layer_id == layer),
                        0,
                    )))
                context = "\n\n".join(chunk for chunk in chunks if chunk)
                context = trim_memory_to_budget(context, budget_tokens)
                actual_tokens = estimate_memory_tokens(context)
                mode = "per_layer_reader"
            elif not self.strict:
                context = self.manager.prefetch_all(query, session_id=session_id, strict=True)
                context = trim_memory_to_budget(context or "", budget_tokens)
                actual_tokens = estimate_memory_tokens(context)
        elif not self.strict:
            context = self.manager.prefetch_all(query, session_id=session_id, strict=True)
            context = trim_memory_to_budget(context or "", budget_tokens)
            actual_tokens = estimate_memory_tokens(context)
        selection = replace(selection, actual_tokens=actual_tokens, enforcement_mode=mode)
        return MemoryHookResult(
            selection=selection, context=context, source_scope=self.source_scope
        )

    def after_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        self.manager.sync_all(
            user_content,
            assistant_content,
            session_id=session_id,
            messages=messages,
        )
        self.manager.queue_prefetch_all(user_content, session_id=session_id)

    def before_compress(self, messages: list[dict[str, Any]]) -> str:
        return self.manager.on_pre_compress(messages)

    def session_end(self, messages: list[dict[str, Any]]) -> None:
        self.manager.on_session_end(messages)


DEFAULT_OPTIMIZATION_LOOPS: tuple[OptimizationLoop, ...] = (
    OptimizationLoop("runtime_wake", "bootstrap", 0, "OBSERVE"),
    OptimizationLoop("context_freshness", "sense", 20),
    OptimizationLoop("memory_integrity", "sense", 20),
    OptimizationLoop("epistemic_gate", "reason", 20),
    OptimizationLoop("goal_review", "goals", 20),
    OptimizationLoop("skill_candidate", "learn", 20),
    OptimizationLoop("workflow_candidate", "learn", 20),
    OptimizationLoop("execution_verification", "measure", 20),
    OptimizationLoop("learning_measurement", "measure", 20),
    OptimizationLoop("rollback_observability", "measure", 20),
)


@dataclass(frozen=True)
class RuntimeWake:
    """Read-only bootstrap event emitted when the Hermes runtime opens."""

    owner: str
    steward: str
    opened_at: str
    active_loops: tuple[str, ...]
    projection: str = "code"
    action_allowed: bool = False


@dataclass(frozen=True)
class ModelRouting:
    """Role-to-substrate routing; IDs are configuration, never identity."""

    designer_reviewer: str = "configured.designer_reviewer"
    builder: str = "configured.builder"
    builder_fallbacks: tuple[str, ...] = (
        "configured.local_120b",
        "configured.local_671b",
    )
    landing_gate: str = "configured.landing_gate"


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model_ref: str | None
    max_output_tokens: int
    quality_floor: float
    rationale: str


@dataclass(frozen=True)
class ModelRouteTelemetry:
    task: str
    model_ref: str | None
    quality_floor: float
    resolver_latency_ms: float
    resolved: bool


class CostAwareModelRouter:
    """Route cheap deterministic work away from expensive reasoning models.

    ``model_ref`` values are configuration keys, not hardcoded model IDs. The
    caller resolves them through Hermes' provider/model configuration.
    """

    def __init__(
        self,
        routing: ModelRouting | None = None,
        *,
        resolver: Callable[[str], str] | None = None,
    ):
        self.routing = routing or ModelRouting()
        self.resolver = resolver
        self.telemetry: list[ModelRouteTelemetry] = []

    def _resolve(self, role: str) -> tuple[str, float]:
        if self.resolver is None:
            raise RuntimeError(f"dynamic model resolver is required for role '{role}'")
        started = time.perf_counter()
        model_ref = self.resolver(role)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not model_ref or not isinstance(model_ref, str):
            raise RuntimeError(f"dynamic model resolver returned no model for role '{role}'")
        return model_ref, latency_ms

    def route(self, task: str, *, complexity: str = "normal") -> ModelRoute:
        if task in {"retrieve", "memory_select", "freshness", "verify"}:
            return ModelRoute(task, None, 0, 1.0, "deterministic/no LLM")
        if task in {"sense", "classify", "summarize"}:
            model_ref, latency_ms = self._resolve("builder")
            route = ModelRoute(task, model_ref, 512, 0.80, "cheap configured route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            return route
        if task in {"design", "review", "epistemic"}:
            budget = 4096 if complexity == "high" else 2048
            model_ref, latency_ms = self._resolve("designer_reviewer")
            route = ModelRoute(task, model_ref, budget, 0.95, "quality-critical live-resolved route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            return route
        if task == "build":
            model_ref, latency_ms = self._resolve("builder")
            route = ModelRoute(task, model_ref, 4096, 0.90, "builder live-resolved route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            return route
        return ModelRoute(task, self.routing.builder_fallbacks[0], 1024, 0.85, "safe default")


@dataclass(frozen=True)
class LearningMeasurement:
    metric: str
    baseline: float
    after: float
    confidence: float
    validated: bool = False
    skill_or_workflow: str = ""

    @property
    def delta(self) -> float:
        return self.after - self.baseline

    @property
    def improved(self) -> bool:
        return self.validated and self.delta > 0

    def to_event(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "baseline": self.baseline,
            "after": self.after,
            "delta": self.delta,
            "confidence": self.confidence,
            "validated": self.validated,
            "improved": self.improved,
            "skill_or_workflow": self.skill_or_workflow,
        }


@dataclass(frozen=True)
class MemorySnapshot:
    """Explicit snapshot of the configured memory-layer registry."""

    layers: tuple[str, ...]
    available: tuple[str, ...]
    missing: tuple[str, ...]
    provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    facts: Mapping[str, Any]
    uncertainties: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    memory: MemorySnapshot | None = None


@dataclass(frozen=True)
class Reasoning:
    conclusion: str
    confidence: float
    rationale: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    needs_more_evidence: bool = False


@dataclass(frozen=True)
class GoalProposal:
    title: str
    rationale: str
    priority: int = 2


@dataclass(frozen=True)
class ActionProposal:
    description: str
    risk: str = "low"
    reversible: bool = True
    requires_morten: bool = True
    requires_landing_gate: bool = False
    rollback: str | None = None
    mutates_code: bool = False
    idempotency_key: str = ""


@dataclass(frozen=True)
class ApprovalDecision:
    operator_approved: bool = False
    morten_approved: bool = False
    reviewer_pass: bool = False


class ActionGate:
    """Fail-closed action authorization for the Code pipeline."""

    @staticmethod
    def allows(action: ActionProposal, decision: ApprovalDecision | bool) -> bool:
        risk = str(action.risk).strip().lower()
        if risk not in {"low", "medium", "high", "critical", "irreversible"}:
            return False
        if isinstance(decision, bool):
            # A bare bool is intentionally insufficient for gated actions.
            return bool(decision) and not action.requires_morten and not action.requires_landing_gate and not action.mutates_code
        if not decision.operator_approved:
            return False
        if risk in {"high", "critical", "irreversible"} and not decision.morten_approved:
            return False
        if action.requires_morten and not decision.morten_approved:
            return False
        if action.requires_landing_gate and not decision.reviewer_pass:
            return False
        if action.mutates_code and not decision.reviewer_pass:
            return False
        if not action.reversible and not decision.morten_approved:
            return False
        return True


@dataclass(frozen=True)
class TickResult:
    tick_id: str
    started_at: str
    finished_at: str
    outcome: LoopOutcome
    observation: Observation
    reasoning: Reasoning
    goals: tuple[GoalProposal, ...] = ()
    action: ActionProposal | None = None
    action_result: Mapping[str, Any] | None = None
    learning_event: Mapping[str, Any] | None = None
    model_routing: ModelRouting = field(default_factory=ModelRouting)
    memory_selection: MemorySelection | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        return data


class PipelineAdapter(Protocol):
    def sense(self, memory: MemorySnapshot) -> Observation: ...

    def reason(self, observation: Observation, routing: ModelRouting) -> Reasoning: ...

    def propose_goals(self, observation: Observation, reasoning: Reasoning) -> Sequence[GoalProposal]: ...

    def propose_action(self, observation: Observation, reasoning: Reasoning) -> ActionProposal | None: ...

    def execute(self, action: ActionProposal, routing: ModelRouting) -> Mapping[str, Any]: ...

    def learn(self, result: TickResult) -> Mapping[str, Any]: ...


class MemoryProvider(Protocol):
    def snapshot(self, layers: Sequence[str]) -> MemorySnapshot: ...


class FileMemoryProvider:
    """Reads a JSON registry and reports missing layers instead of guessing."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    def snapshot(self, layers: Sequence[str]) -> MemorySnapshot:
        raw: Mapping[str, Any] = {}
        if self.path.exists():
            try:
                candidate = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    raw = candidate
            except (OSError, json.JSONDecodeError):
                raw = {}
        available = tuple(layer for layer in layers if layer in raw)
        missing = tuple(layer for layer in layers if layer not in raw)
        provenance = {
            layer: str(raw[layer].get("provenance", "unknown"))
            if isinstance(raw[layer], dict)
            else "unknown"
            for layer in available
        }
        return MemorySnapshot(tuple(layers), available, missing, provenance)


class JsonStateStore:
    """Atomic state/output store suitable for one tick at a time."""

    _lock = threading.RLock()

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    def append(self, result: TickResult) -> None:
        with self._lock:
            self._append_locked(result)

    def _append_locked(self, result: TickResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    records = loaded
            except (OSError, json.JSONDecodeError):
                records = []
        records.append(result.to_dict())
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(records[-100:], handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


class ExecutionLedger:
    """Atomic crash-safe execution ledger keyed by idempotency key."""

    _lock = threading.RLock()

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _guard(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or any(v not in {"started", "completed"} for v in data.values()):
                raise ValueError("invalid execution ledger schema")
            return dict(data)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"execution ledger unreadable; refusing retry: {exc}") from exc

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def claim(self, key: str) -> bool:
        if not key:
            raise ValueError("idempotency key is required")
        with self._lock:
            guard = self._guard()
            try:
                data = self._read()
                if key in data:
                    return False
                data[key] = "started"
                self._write(data)
                return True
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
                guard.close()

    def complete(self, key: str) -> None:
        with self._lock:
            guard = self._guard()
            try:
                data = self._read()
                if data.get(key) != "started":
                    raise ValueError("execution was not claimed")
                data[key] = "completed"
                self._write(data)
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
                guard.close()

    def status(self, key: str) -> str | None:
        guard = self._guard()
        try:
            return self._read().get(key)
        finally:
            fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
            guard.close()


class ContinuousPipeline:
    def __init__(
        self,
        adapter: PipelineAdapter,
        memory: MemoryProvider,
        *,
        state: JsonStateStore | None = None,
        memory_layers: Sequence[str] = (),
        memory_scheduler: MemoryScheduler | None = None,
        memory_token_budget: int = 1800,
        memory_phase: str = "sense",
        routing: ModelRouting | None = None,
        router: CostAwareModelRouter | None = None,
        execution_ledger: ExecutionLedger | None = None,
        require_live_router: bool = True,
        approval: Callable[[ActionProposal], ApprovalDecision | bool] | None = None,
    ):
        self.adapter = adapter
        self.memory = memory
        self.state = state
        self.memory_layers = tuple(memory_layers)
        self.memory_scheduler = memory_scheduler
        self.memory_token_budget = memory_token_budget
        self.memory_phase = memory_phase
        self.routing = routing or ModelRouting()
        self.router = router
        self.execution_ledger = execution_ledger
        self.require_live_router = require_live_router
        self.approval = approval or (lambda action: False)

    def _resolve_runtime_routing(self) -> ModelRouting:
        if self.router is None:
            if self.require_live_router:
                raise RuntimeError("live model router is required for pipeline execution")
            return self.routing
        builder = self.router.route("build").model_ref
        reviewer = self.router.route("review").model_ref
        if not builder or not reviewer:
            raise RuntimeError("live model router returned incomplete runtime routing")
        self.routing = replace(
            self.routing,
            builder=builder,
            designer_reviewer=reviewer,
        )
        return self.routing

    def tick(self) -> TickResult:
        started = _now()
        self._resolve_runtime_routing()
        tick_id = uuid.uuid4().hex
        selection = None
        layers = self.memory_layers
        if self.memory_scheduler is not None:
            selection = self.memory_scheduler.select(
                phase=self.memory_phase,
                budget_tokens=self.memory_token_budget,
            )
            layers = selection.selected
        memory = self.memory.snapshot(layers)
        observation = self.adapter.sense(memory)
        if observation.memory is None:
            observation = Observation(
                facts=observation.facts,
                uncertainties=observation.uncertainties,
                sources=observation.sources,
                memory=memory,
            )
        reasoning = self.adapter.reason(observation, self.routing)
        proposed_goals = (
            tuple(self.adapter.propose_goals(observation, reasoning))
            if not reasoning.needs_more_evidence and reasoning.confidence >= 0.95
            else ()
        )
        goals = proposed_goals
        action = self.adapter.propose_action(observation, reasoning)

        # Epistemic gate: uncertainty or low confidence never becomes ACT.
        approved = (
            action is not None
            and not reasoning.needs_more_evidence
            and reasoning.confidence >= 0.95
            and not memory.missing
        )
        if approved and action is not None:
            try:
                approved = ActionGate.allows(action, self.approval(action))
            except Exception:
                # A broken approval channel must never turn into execution.
                approved = False
        if approved and action is not None and self.execution_ledger is None:
            approved = False
        if approved and action is not None and self.execution_ledger is not None:
            if not action.idempotency_key or not self.execution_ledger.claim(action.idempotency_key):
                approved = False
        if approved and action is not None and self.router is None:
            approved = False
        outcome = LoopOutcome.ACT if approved else LoopOutcome.PROPOSE if action else LoopOutcome.OBSERVE
        action_result = self.adapter.execute(action, self.routing) if approved and action else None
        if approved and action is not None and self.execution_ledger is not None:
            self.execution_ledger.complete(action.idempotency_key)

        provisional = TickResult(
            tick_id=tick_id,
            started_at=started,
            finished_at=_now(),
            outcome=outcome,
            observation=observation,
            reasoning=reasoning,
            goals=goals,
            action=action,
            action_result=action_result,
            model_routing=self.routing,
            memory_selection=selection,
        )
        learning = self.adapter.learn(provisional)
        if isinstance(learning, Mapping) and learning.get("improved") is True and learning.get("validated") is not True:
            raise RuntimeError("unvalidated learning improvement cannot be accepted")
        result = replace(provisional, learning_event=learning)
        if self.state:
            self.state.append(result)
        return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_open(
    *,
    now: Callable[[], str] = _now,
    loops: Sequence[OptimizationLoop] = DEFAULT_OPTIMIZATION_LOOPS,
) -> RuntimeWake:
    """Create a fail-closed wake event; it never executes an action."""
    return RuntimeWake(
        owner=CODE_OWNER,
        steward=FABER_STEWARD,
        opened_at=now(),
        active_loops=tuple(loop.loop_id for loop in loops),
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run one Hermes continuous-agent tick.")
    parser.add_argument("--memory-registry", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--memory-layer", action="append", default=[])
    args = parser.parse_args()
    raise SystemExit(
        "No adapter configured. Embed ContinuousPipeline in Hermes with a model/tool adapter; "
        "the standalone command intentionally fails closed."
    )


if __name__ == "__main__":
    _cli()
