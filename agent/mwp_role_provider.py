"""Fail-closed role/provider validation for MWP adaptive routing.

This module validates metadata only. It never resolves secrets, starts a model,
changes config, routes a task, or claims that a catalog match is live runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class BindingVerdict(str):
    CONSISTENT = "CONSISTENT"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class RoleProviderBinding:
    agent_id: str
    role: str
    model: str
    provider: str
    runtime: str = ""


@dataclass(frozen=True)
class BindingReadback:
    agent_id: str
    role: str
    model: str
    provider: str
    verdict: str
    catalog_matches: tuple[str, ...]
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "model": self.model,
            "provider": self.provider,
            "verdict": self.verdict,
            "catalog_matches": list(self.catalog_matches),
            "blockers": list(self.blockers),
            "raw_payload_included": False,
        }


def _catalog_models(catalog: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    providers = catalog.get("providers", {})
    if not isinstance(providers, Mapping):
        return ()
    for provider, data in providers.items():
        if not isinstance(data, Mapping):
            continue
        models = data.get("models", [])
        if not isinstance(models, list):
            continue
        for item in models:
            if isinstance(item, Mapping) and item.get("id"):
                rows.append((str(provider), str(item["id"])))
    return tuple(rows)


def _provider_family(provider: str) -> str:
    value = provider.lower().strip()
    if value.startswith("openai"):
        return "openai"
    if value.startswith("anthropic"):
        return "anthropic"
    if value.startswith("openrouter"):
        return "openrouter"
    return value


def _model_matches(catalog_model: str, binding_model: str, provider: str) -> bool:
    """Match catalog-qualified ids to the provider's runtime model id.

    Catalogs commonly publish ``provider/model`` while runtime metadata for
    native providers publishes only ``model``.  The provider family remains a
    separate check; this helper only removes the redundant native prefix.
    """
    if catalog_model == binding_model:
        return True
    prefix = f"{_provider_family(provider)}/"
    return catalog_model == f"{prefix}{binding_model}"


def validate_binding(binding: RoleProviderBinding, catalog: Mapping[str, Any]) -> BindingReadback:
    if not binding.agent_id.strip() or not binding.role.strip() or not binding.model.strip() or not binding.provider.strip():
        raise ValueError("agent_id, role, model and provider are required")
    rows = _catalog_models(catalog)
    exact = tuple(provider for provider, model in rows if _model_matches(model, binding.model, provider))
    family = _provider_family(binding.provider)
    family_matches = tuple(
        provider for provider, model in rows
        if _model_matches(model, binding.model, provider) and _provider_family(provider) == family
    )
    if not exact:
        verdict = BindingVerdict.UNVERIFIED
        blockers = ("model absent from catalog", "live runtime receipt required")
    elif not family_matches:
        verdict = BindingVerdict.MISMATCH
        blockers = ("provider family does not own catalog model", "live runtime receipt required")
    else:
        verdict = BindingVerdict.CONSISTENT
        blockers = ("live runtime receipt required",)
    return BindingReadback(
        agent_id=binding.agent_id,
        role=binding.role,
        model=binding.model,
        provider=binding.provider,
        verdict=verdict,
        catalog_matches=exact,
        blockers=blockers,
    )


def validate_bindings(bindings: Iterable[RoleProviderBinding], catalog: Mapping[str, Any]) -> tuple[BindingReadback, ...]:
    return tuple(validate_binding(binding, catalog) for binding in bindings)
