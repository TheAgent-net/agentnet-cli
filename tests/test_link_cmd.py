"""Tests for link CLI commands."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from agentnet_cli.main import app

runner = CliRunner()


class TestLinkAuth:
    @patch("agentnet_cli.commands.link.LinkClient")
    def test_auth_login(self, MockLink, fake_home):
        MockLink.return_value.auth_login.return_value = {
            "verification_url": "https://link.com/verify",
            "user_code": "ABCD",
        }
        result = runner.invoke(app, ["link", "auth", "--client-name", "test-agent"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["verification_url"] == "https://link.com/verify"

    @patch("agentnet_cli.commands.link.LinkClient")
    def test_auth_login_error(self, MockLink, fake_home):
        from agentnet_cli.payments.link import LinkError

        MockLink.return_value.auth_login.side_effect = LinkError("timeout")
        result = runner.invoke(app, ["link", "auth", "--client-name", "test"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert "timeout" in data["error"]


class TestLinkStatus:
    @patch("agentnet_cli.commands.link.LinkClient")
    def test_status_authenticated(self, MockLink, fake_home):
        MockLink.return_value.auth_status.return_value = {
            "authenticated": True,
            "email": "user@test.com",
        }
        result = runner.invoke(app, ["link", "status"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["authenticated"] is True


class TestLinkMethods:
    @patch("agentnet_cli.commands.link.LinkClient")
    def test_lists_methods(self, MockLink, fake_home):
        MockLink.return_value.list_payment_methods.return_value = {
            "payment_methods": [{"id": "pm_1", "type": "card"}],
        }
        result = runner.invoke(app, ["link", "methods"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["payment_methods"]) == 1
