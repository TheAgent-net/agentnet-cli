"""Tests for MCP payment tools."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agentnet_cli.mcp.tools import ToolHandlers
from agentnet_cli.payments.mpp_flow import PaymentFlowError


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
    @patch("agentnet_cli.mcp.tools.MppPaymentClient")
    def test_pay_non_402(self, MockMpp):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": False,
            "status_code": 200,
            "body": {"data": "free"},
            "headers": {},
        }
        result = _make_handlers().pay(url="https://api.test/free")
        assert result["status_code"] == 200

    @patch("agentnet_cli.mcp.tools.execute_mpp_payment")
    @patch("agentnet_cli.mcp.tools.MppPaymentClient")
    def test_pay_rejects_over_limit(self, MockMpp, mock_execute):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 99900},
            "headers": {"www-authenticate": 'Payment method="stripe"'},
        }
        mock_execute.side_effect = PaymentFlowError(
            "Payment of $999.00 exceeds spend limit (max $25.00)"
        )
        with pytest.raises(ValueError, match="spend limit"):
            _make_handlers().pay(url="https://api.test/expensive")

    @patch("agentnet_cli.mcp.tools.execute_mpp_payment")
    @patch("agentnet_cli.mcp.tools.MppPaymentClient")
    def test_pay_full_lifecycle(self, MockMpp, mock_execute):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {
                "amount_minor": 150,
                "agent_name": "TestBot",
                "description": "A test agent",
            },
            "headers": {"www-authenticate": 'Payment id="x", method="stripe"'},
        }
        mock_execute.return_value = {"status": "success", "receipt_ref": "pi_abc"}

        result = _make_handlers().pay(url="https://api.test/paid")
        assert result["status"] == "success"

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["url"] == "https://api.test/paid"
        assert call_kwargs["max_amount"] == 25.0
        assert call_kwargs["via"] == "MCP"

    @patch("agentnet_cli.mcp.tools.execute_mpp_payment")
    @patch("agentnet_cli.mcp.tools.MppPaymentClient")
    def test_pay_x402_not_supported(self, MockMpp, mock_execute):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 100},
            "headers": {"payment-required": "base64data"},
        }
        mock_execute.side_effect = PaymentFlowError("x402 crypto payments not yet supported")
        with pytest.raises(ValueError, match="x402"):
            _make_handlers().pay(url="https://api.test/x402")
