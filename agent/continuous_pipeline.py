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
import urllib.error
import urllib.request
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
    source_scope: str = "hermes.session"


class MemoryManagerBridge:
    """Adapter around Hermes' existing MemoryManager lifecycle.

    The bridge adds selection/budget observability without replacing provider
    storage, scopes, or hook semantics. Provider-specific retrieval remains
    authoritative until the canonical layer registry exposes per-layer reads.
    """

    def __init__(self, manager: Any, scheduler: MemoryScheduler, *, strict: bool = False, metrics_path: str | os.PathLike[str] | None = None, source_scope: str = "hermes.session"):
        self.manager = manager
        self.scheduler = scheduler
        self.strict = strict
        self.metrics_path = Path(metrics_path).expanduser() if metrics_path else None
        self.source_scope = source_scope
        self.per_layer_calls = 0
        self.aggregate_fallback_calls = 0

    def _persist_metrics(self) -> None:
        if self.metrics_path is None:
            return
        payload = {
            "per_layer_calls": self.per_layer_calls,
            "aggregate_fallback_calls": self.aggregate_fallback_calls,
            "total_calls": self.per_layer_calls + self.aggregate_fallback_calls,
            "fallback_rate": (
                self.aggregate_fallback_calls / (self.per_layer_calls + self.aggregate_fallback_calls)
                if self.per_layer_calls + self.aggregate_fallback_calls else 0.0
            ),
            "strict": self.strict,
        }
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.metrics_path.with_suffix(self.metrics_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.metrics_path)

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
                self.per_layer_calls += 1
                self._persist_metrics()
            else:
                self.aggregate_fallback_calls += 1
                self._persist_metrics()
                if self.strict:
                    raise RuntimeError("per-layer reader required for strict memory enforcement")
                context = self.manager.prefetch_all(query, session_id=session_id, strict=True)
                context = trim_memory_to_budget(context or "", budget_tokens)
                actual_tokens = estimate_memory_tokens(context)
        else:
            self.aggregate_fallback_calls += 1
            self._persist_metrics()
            if self.strict:
                raise RuntimeError("per-layer reader required for strict memory enforcement")
            context = self.manager.prefetch_all(query, session_id=session_id, strict=True)
            context = trim_memory_to_budget(context or "", budget_tokens)
            actual_tokens = estimate_memory_tokens(context)
        selection = replace(selection, actual_tokens=actual_tokens, enforcement_mode=mode)
        return MemoryHookResult(selection=selection, context=context, source_scope=self.source_scope)

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


def _configured_hermes_model(provider: str) -> str | None:
    """Read a model reference from Hermes' canonical config loader.

    Do not scan YAML as text here: a primary ``model.provider`` section is
    commonly followed by ``fallback_providers`` and a bounded text window can
    accidentally attribute a fallback model to the primary route.  This
    resolver is used by governed pipeline routing, so primary and fallback
    provider identity must remain distinct.
    """
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
    except Exception:
        return None

    model_config = config.get("model") or {}
    if not isinstance(model_config, dict):
        model_config = {}
    configured_provider = str(model_config.get("provider") or "").strip().lower()
    default_model = str(model_config.get("default") or "").strip()
    requested_provider = str(provider or "").strip().lower()

    # ``custom`` is the historical role for the active/default model route;
    # preserve that contract without treating a fallback entry as primary.
    if requested_provider == "custom":
        return default_model or None
    if configured_provider == requested_provider:
        return default_model or None

    fallbacks = config.get("fallback_providers") or []
    if isinstance(fallbacks, list):
        for entry in fallbacks:
            if not isinstance(entry, dict):
                continue
            entry_provider = str(entry.get("provider") or "").strip().lower()
            if entry_provider == requested_provider:
                fallback_model = str(entry.get("model") or "").strip()
                return fallback_model or None
    return None


def default_live_model_resolver(role: str) -> str:
    """Resolve governed role routes from live configuration; fail closed."""
    env_by_role = {
        "designer": ("HERMES_SOL_MODEL", "HERMES_DESIGNER_MODEL"),
        "reviewer": ("HERMES_SOL_MODEL", "HERMES_REVIEWER_MODEL"),
        "designer_reviewer": ("HERMES_SOL_MODEL", "HERMES_DESIGNER_REVIEWER_MODEL"),
        "builder": ("HERMES_LUNA_MODEL", "HERMES_BUILDER_MODEL"),
        "builder_120b": ("HERMES_120B_MODEL",),
        "builder_671b": ("HERMES_671B_MODEL",),
    }
    if role not in env_by_role:
        raise RuntimeError(f"unsupported live model role: {role}")
    for key in env_by_role[role]:
        model = os.environ.get(key, "").strip()
        if model:
            return model
    if role == "builder":
        model = _configured_hermes_model("openai-api")
        if model:
            return model
    if role == "builder_120b":
        model = _configured_hermes_model("custom")
        if model:
            return model
    if role in {"designer", "reviewer", "designer_reviewer", "builder_671b"}:
        base = os.environ.get("OPUS_REASONER_URL", "http://192.168.40.13:1234/v1").rstrip("/")
        url = base.removesuffix("/v1") + "/api/v0/models"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                items = (json.load(response).get("data") or [])
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"live Cortex/Sol resolver unavailable: {exc}") from exc
        candidates = [
            item for item in items
            if isinstance(item, dict)
            and item.get("id")
            and "embed" not in str(item.get("id", "")).lower()
            and "120b" not in str(item.get("id", "")).lower()
            and "gpt-oss" not in str(item.get("arch", "")).lower()
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"live Cortex/Sol resolver expected one candidate, got {len(candidates)}")
        capabilities = candidates[0].get("capabilities") or []
        if "tool_use" not in capabilities:
            raise RuntimeError("live Cortex/Sol candidate lacks tool_use")
        return str(candidates[0]["id"])
    raise RuntimeError(f"live model route is required for role '{role}'")


@dataclass(frozen=True)
class ModelRouting:
    """Role-to-substrate routing; IDs are configuration, never identity."""

    designer_reviewer: str = "configured.sol"
    designer: str = "configured.sol"
    reviewer: str = "configured.sol"
    builder: str = "configured.luna"
    builder_fallbacks: tuple[str, ...] = (
        "configured.120b",
        "configured.671b",
    )
    landing_gate: str = "configured.claude"


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
    estimated_cost: float = 0.0
    actual_quality: float | None = None
    execution_latency_ms: float | None = None


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
        telemetry_path: str | os.PathLike[str] | None = None,
    ):
        self.routing = routing or ModelRouting()
        self.resolver = resolver
        self.telemetry_path = Path(telemetry_path).expanduser() if telemetry_path else None
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

    def _persist_telemetry(self) -> None:
        if self.telemetry_path is None:
            return
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.telemetry_path.with_suffix(self.telemetry_path.suffix + ".tmp")
        tmp.write_text(json.dumps([asdict(item) for item in self.telemetry], indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.telemetry_path)

    def record_outcome(
        self,
        *,
        task: str,
        actual_quality: float,
        execution_latency_ms: float,
        estimated_cost: float,
    ) -> None:
        """Attach measured task outcome to the latest matching route."""
        if not 0.0 <= actual_quality <= 1.0:
            raise ValueError("actual_quality must be between 0 and 1")
        for index in range(len(self.telemetry) - 1, -1, -1):
            item = self.telemetry[index]
            if item.task == task:
                self.telemetry[index] = replace(
                    item,
                    actual_quality=actual_quality,
                    execution_latency_ms=execution_latency_ms,
                    estimated_cost=estimated_cost,
                )
                self._persist_telemetry()
                return
        raise KeyError(f"no route telemetry exists for task '{task}'")

    def route(self, task: str, *, complexity: str = "normal") -> ModelRoute:
        if task in {"retrieve", "memory_select", "freshness", "verify"}:
            return ModelRoute(task, None, 0, 1.0, "deterministic/no LLM")
        if task in {"sense", "classify", "summarize"}:
            model_ref, latency_ms = self._resolve("builder")
            route = ModelRoute(task, model_ref, 512, 0.80, "Luna configured route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            self._persist_telemetry()
            return route
        if task in {"design", "review", "epistemic"}:
            budget = 4096 if complexity == "high" else 2048
            role = "designer" if task == "design" else "reviewer"
            model_ref, latency_ms = self._resolve(role)
            route = ModelRoute(task, model_ref, budget, 0.95, "Sol quality-critical live-resolved route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            self._persist_telemetry()
            return route
        if task == "build":
            model_ref, latency_ms = self._resolve("builder")
            route = ModelRoute(task, model_ref, 4096, 0.90, "Luna builder live-resolved route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            self._persist_telemetry()
            return route
        if task in {"build_120b", "build_671b"}:
            role = "builder_120b" if task == "build_120b" else "builder_671b"
            model_ref, latency_ms = self._resolve(role)
            route = ModelRoute(task, model_ref, 8192, 0.95, f"{role} live-resolved heavy builder route")
            self.telemetry.append(ModelRouteTelemetry(task, model_ref, route.quality_floor, latency_ms, True))
            self._persist_telemetry()
            return route
        raise RuntimeError(f"no governed model route for task '{task}'")


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


class LearningMeasurementStore:
    """Durable before/after learning evidence; unvalidated gains never count."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    def record(self, measurement: LearningMeasurement) -> dict[str, Any]:
        if not measurement.metric.strip():
            raise ValueError("learning metric is required")
        if not 0.0 <= measurement.confidence <= 1.0:
            raise ValueError("learning confidence must be between 0 and 1")
        if measurement.validated and not measurement.skill_or_workflow.strip():
            raise ValueError("validated learning requires skill_or_workflow")
        event = measurement.to_event()
        existing: list[dict[str, Any]] = []
        if self.path.exists():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    raise ValueError("learning store must contain a list")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError(f"learning store unreadable: {exc}") from exc
        existing.append(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        return event


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
    goal_id: str = ""
    cad_ref: str = ""
    adr_ref: str = ""
    bl_ref: str = ""
    risk: str = "low"
    rollback: str = ""
    job_spec: Mapping[str, Any] = field(default_factory=dict)
    trace_id: str = ""


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
    proposal_results: tuple[Mapping[str, Any], ...] = ()
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
        goal_sink: Callable[[GoalProposal], Mapping[str, Any] | None] | None = None,
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
        self.router = router or (
            CostAwareModelRouter(
                resolver=default_live_model_resolver,
                telemetry_path=os.environ.get("HERMES_FABER_ROUTING_TELEMETRY", "~/.hermes-gui/faber/routing-telemetry.json"),
            )
            if require_live_router
            else None
        )
        self.execution_ledger = execution_ledger
        self.require_live_router = require_live_router
        self.goal_sink = goal_sink
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
            designer=reviewer,
            reviewer=reviewer,
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
            tuple(replace(goal, trace_id=tick_id) for goal in self.adapter.propose_goals(observation, reasoning))
            if not reasoning.needs_more_evidence and reasoning.confidence >= 0.95
            else ()
        )
        goals = proposed_goals
        proposal_results: tuple[Mapping[str, Any], ...] = ()
        if self.goal_sink is not None and goals:
            try:
                proposal_results = tuple(dict(self.goal_sink(goal) or {}) for goal in goals)
            except Exception as exc:
                raise RuntimeError(f"Faber goal proposal sink failed: {exc}") from exc
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
            proposal_results=proposal_results,
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
