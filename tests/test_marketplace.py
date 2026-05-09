import json

import pytest

from agentnet_cli.marketplace import die, get_agent_id, get_client, output


def test_get_client_from_env(fake_home, monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "env-tok")
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://test.example.com")
    client = get_client()
    assert client._token == "env-tok"
    assert client._base == "https://test.example.com"


def test_get_client_from_config(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "cfg-tok", "platform_url": "https://cfg.example.com"})
    client = get_client()
    assert client._token == "cfg-tok"
    assert client._base == "https://cfg.example.com"


def test_get_client_env_overrides_config(fake_home, monkeypatch):
    from agentnet_cli.config import save_config

    save_config({"api_token": "cfg-tok", "platform_url": "https://cfg.example.com"})
    monkeypatch.setenv("AGENTNET_TOKEN", "env-tok")
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://env.example.com")
    client = get_client()
    assert client._token == "env-tok"
    assert client._base == "https://env.example.com"


def test_get_client_no_auth(fake_home):
    with pytest.raises(SystemExit) as exc_info:
        get_client()
    assert exc_info.value.code == 1


def test_get_client_default_platform_url(fake_home, monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "tok")
    client = get_client()
    assert client._base == "https://app.agentnet.market"


def test_get_agent_id_from_config(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "t", "agent_id": "agent-123"})
    assert get_agent_id() == "agent-123"


def test_get_agent_id_missing(fake_home):
    with pytest.raises(SystemExit) as exc_info:
        get_agent_id()
    assert exc_info.value.code == 1


def test_get_agent_id_no_agent_id_key(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "t"})
    with pytest.raises(SystemExit) as exc_info:
        get_agent_id()
    assert exc_info.value.code == 1


def test_output(capsys):
    output({"status": "ok", "count": 3})
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == {"status": "ok", "count": 3}


def test_die(capsys):
    with pytest.raises(SystemExit) as exc_info:
        die("something broke")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == {"error": "something broke"}
