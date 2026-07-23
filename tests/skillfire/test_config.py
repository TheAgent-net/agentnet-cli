from unittest.mock import patch

from agentnet_cli.tools.skillfire import config


def test_resolve_credentials_from_env(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "envtok")
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert config.resolve_credentials() == ("envtok", "https://app.agentnet.market")


def test_resolve_credentials_none_without_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert config.resolve_credentials() is None
