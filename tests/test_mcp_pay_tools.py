"""Tests for MCP payment tools."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agentnet_cli.mcp.tools import ToolHandlers


def _make_handlers():
    return ToolHandlers(
        platform_url="https://test.agentnet.market",
        api_token="test_token",
        agent_id="agent_test",
    )


class TestLinkAuthTool:
    @patch("agentnet_cli.mcp.tools.LinkClient")
    def test_link_auth_returns_verification_url(self, MockLink):
        MockLink.return_value.auth_login.return_value = {
            "verification_url": "https://link.com/verify",
            "user_code": "ABCD",
        }
        result = _make_handlers().link_auth(client_name="test-agent")
        assert result["verification_url"] == "https://link.com/verify"

    @patch("agentnet_cli.mcp.tools.LinkClient")
    def test_link_status(self, MockLink):
        MockLink.return_value.auth_status.return_value = {"authenticated": True}
        result = _make_handlers().link_status()
        assert result["authenticated"] is True


class TestPayTool:
    @patch("agentnet_cli.mcp.tools.SpendController")
    @patch("agentnet_cli.mcp.tools.MppPaymentClient")
    def test_pay_non_402(self, MockMpp, MockCtrl):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": False,
            "status_code": 200,
            "body": {"data": "free"},
            "headers": {},
        }
        MockCtrl.return_value.check_allowed.return_value = True
        result = _make_handlers().pay(url="https://api.test/free")
        assert result["status_code"] == 200

    @patch("agentnet_cli.mcp.tools.SpendController")
    @patch("agentnet_cli.mcp.tools.MppPaymentClient")
    def test_pay_rejects_over_limit(self, MockMpp, MockCtrl):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 99900},
            "headers": {"www-authenticate": 'Payment method="stripe"'},
        }
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = False
        with pytest.raises(ValueError, match="spend limit"):
            _make_handlers().pay(url="https://api.test/expensive")
