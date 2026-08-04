"""Tests for guest bootstrap credential helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentnet_cli.infra import credentials
from agentnet_cli.infra.config import load_config, save_config


def test_get_auth_tier_legacy_token_is_authenticated(fake_home):
    save_config({"api_token": "tok", "org_id": "o"})
    assert credentials.get_auth_tier() == credentials.TIER_AUTHENTICATED
    assert credentials.is_authenticated()


def test_get_auth_tier_guest(fake_home):
    save_config({"api_token": "tok", "tier": "guest"})
    assert credentials.get_auth_tier() == credentials.TIER_GUEST
    assert not credentials.is_authenticated()


def test_ensure_guest_credentials_keeps_existing(fake_home):
    save_config({"api_token": "existing", "tier": "guest"})
    cfg = credentials.ensure_guest_credentials()
    assert cfg["api_token"] == "existing"


def test_ensure_guest_credentials_bootstraps(fake_home):
    mock_client = MagicMock()
    mock_client.cli_bootstrap.return_value = {
        "api_token": "ank1_guest",
        "org_id": "org_guest_abc",
        "agent_id": "agt_1",
        "tier": "guest",
    }
    with patch("agentnet_cli.marketplace.client.PlatformClient", return_value=mock_client):
        cfg = credentials.ensure_guest_credentials(platform_url="http://localhost:8000")

    assert cfg["api_token"] == "ank1_guest"
    assert cfg["tier"] == "guest"
    assert cfg["agent_id"] == "agt_1"
    assert load_config()["api_token"] == "ank1_guest"
    mock_client.cli_bootstrap.assert_called_once()
    mock_client.close.assert_called_once()
