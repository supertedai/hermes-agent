"""Metadata-only world-model alignment projection into topology context."""
from __future__ import annotations

from typing import Any, Mapping

from agent.mwp_topology_context import project_topology_context


def attach_world_model_status(topology: Mapping[str, Any], hub: Mapping[str, Any]) -> dict[str, Any]:
    """Attach only world-model status/provenance/freshness, never raw hub data."""
    world_model = {
        key: hub[key]
        for key in ("status", "source", "recorded_at", "freshness", "provenance", "owner", "next_action")
        if key in hub
    }
    if not world_model:
        world_model = {"status": "UNKNOWN", "reason": "world-model readback absent"}
    projected = dict(topology)
    projected["world_model"] = world_model
    return project_topology_context(projected)
