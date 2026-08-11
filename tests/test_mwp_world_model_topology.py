from agent.mwp_world_model_topology import attach_world_model_status


def test_world_model_status_projection_is_metadata_only():
    result = attach_world_model_status(
        {"user_id": "morten", "installation_id": "i-a", "login_surface_id": "desktop-a", "raw_payload": "private"},
        {"status": "BLOCKED", "source": ".12:8010", "freshness": "UNKNOWN", "provenance": "openapi-readback", "raw": "private"},
    )
    assert result["world_model"] == {"status": "BLOCKED", "source": ".12:8010", "freshness": "UNKNOWN", "provenance": "openapi-readback"}
    assert "raw_payload" not in result
    assert "raw" not in result["world_model"]


def test_missing_world_model_is_unknown():
    result = attach_world_model_status({"user_id": "morten"}, {})
    assert result["world_model"]["status"] == "UNKNOWN"
