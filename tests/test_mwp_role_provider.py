import pytest

from agent.mwp_role_provider import (
    BindingVerdict,
    RoleProviderBinding,
    validate_binding,
    validate_bindings,
)


CATALOG = {
    "providers": {
        "openai-api": {"models": [{"id": "openai/gpt-5.6-luna"}]},
        "anthropic": {"models": [{"id": "anthropic/claude-sonnet-5"}]},
    }
}


def test_consistent_catalog_family_still_requires_live_receipt():
    result = validate_binding(RoleProviderBinding("a", "reasoner", "openai/gpt-5.6-luna", "openai-api"), CATALOG)
    assert result.verdict == BindingVerdict.CONSISTENT
    assert "live runtime receipt required" in result.blockers


def test_runtime_model_id_matches_provider_qualified_catalog_id():
    result = validate_binding(RoleProviderBinding("a", "reasoner", "gpt-5.6-luna", "openai-api"), CATALOG)
    assert result.verdict == BindingVerdict.CONSISTENT
    assert result.catalog_matches == ("openai-api",)


def test_provider_family_mismatch_is_fail_closed():
    result = validate_binding(RoleProviderBinding("a", "reasoner", "openai/gpt-5.6-luna", "anthropic"), CATALOG)
    assert result.verdict == BindingVerdict.MISMATCH
    assert "provider family does not own catalog model" in result.blockers


def test_local_model_absent_from_catalog_is_unverified():
    result = validate_binding(RoleProviderBinding("a", "worker", "gpt-oss-120b", "openai-api"), CATALOG)
    assert result.verdict == BindingVerdict.UNVERIFIED
    assert result.catalog_matches == ()


def test_batch_validation_is_metadata_only():
    results = validate_bindings([
        RoleProviderBinding("a", "r", "openai/gpt-5.6-luna", "openai-api"),
        RoleProviderBinding("b", "r", "gpt-oss-120b", "openai-api"),
    ], CATALOG)
    assert [item.verdict for item in results] == [BindingVerdict.CONSISTENT, BindingVerdict.UNVERIFIED]
    assert results[0].as_dict()["raw_payload_included"] is False


def test_required_fields_are_enforced():
    with pytest.raises(ValueError, match="agent_id"):
        validate_binding(RoleProviderBinding("", "r", "m", "p"), CATALOG)
