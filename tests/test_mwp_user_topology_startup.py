from tools.mwp_user_topology_startup import device_identity, llm_identity, transport_identity


def test_llm_identity_is_explicit_and_never_guesses():
    missing = llm_identity({})
    assert missing["status"] == "UNVERIFIED"
    assert missing["model"] is None

    live = llm_identity({
        "HERMES_MODEL_PROVIDER": "openai-api",
        "HERMES_MODEL_ID": "gpt-5.6-luna",
        "HERMES_MODEL_ROUTE": "openai-api",
        "HERMES_MODEL_API_MODE": "responses",
    })
    assert live["status"] == "LIVE"
    assert live["provider"] == "openai-api"
    assert live["model"] == "gpt-5.6-luna"


def test_device_identity_is_scoped_and_does_not_expose_hostname():
    result = device_identity({"HOSTNAME": "laptop-example", "HERMES_DEVICE_CLASS": "laptop"})
    assert result["status"] == "LIVE"
    assert result["device_class"] == "laptop"
    assert "laptop-example" not in result["device_id"]


def test_ssh_transport_uses_hashed_hop_reference():
    result = transport_identity({
        "SSH_CONNECTION": "10.0.0.1 50000 10.0.0.2 22",
        "HERMES_GATEWAY_SURFACE": "desktop-ssh",
    })
    assert result["status"] == "LIVE"
    assert result["transport"] == "ssh"
    assert result["ssh_hop_ref"].startswith("ssh-hop-")
    assert "10.0.0.1" not in result["ssh_hop_ref"]