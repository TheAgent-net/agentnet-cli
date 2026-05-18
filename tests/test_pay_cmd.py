"""Tests for pay CLI command."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from agentnet_cli.main import app
from agentnet_cli.payments.mpp_flow import PaymentFlowError

runner = CliRunner()


class TestPayCommand:
    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    def test_pay_non_402_returns_directly(self, MockMpp, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": False,
            "status_code": 200,
            "body": {"data": "free"},
            "headers": {},
        }
        result = runner.invoke(app, ["pay", "https://api.test/free"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status_code"] == 200

    @patch("agentnet_cli.commands.pay.execute_mpp_payment")
    @patch("agentnet_cli.commands.pay.LinkClient")
    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    def test_pay_402_mpp_full_lifecycle(self, MockMpp, MockLink, mock_execute, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {
                "amount_minor": 150,
                "accepted_methods": ["stripe"],
                "agent_name": "TestBot",
                "description": "A test agent",
            },
            "headers": {"www-authenticate": 'Payment id="x", method="stripe"'},
        }
        MockLink.return_value.mpp_decode.return_value = {"networkId": "net_1"}
        mock_execute.return_value = {
            "status": "success",
            "receipt_ref": "pi_abc",
        }

        result = runner.invoke(app, ["pay", "https://api.test/paid"])
        assert result.exit_code == 0

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["url"] == "https://api.test/paid"
        assert call_kwargs["via"] == "marketplace"
        assert call_kwargs["max_amount"] == 25.0

    @patch("agentnet_cli.commands.pay.execute_mpp_payment")
    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    def test_pay_rejects_over_max_amount(self, MockMpp, mock_execute, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 5000},
            "headers": {"www-authenticate": 'Payment method="stripe"'},
        }
        mock_execute.side_effect = PaymentFlowError(
            "Payment of $50.00 exceeds spend limit (max $25.00)"
        )
        result = runner.invoke(app, ["pay", "https://api.test/expensive"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert "exceed" in data["error"].lower() or "limit" in data["error"].lower()

    @patch("agentnet_cli.commands.pay.execute_mpp_payment")
    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    def test_x402_not_supported(self, MockMpp, mock_execute, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 100},
            "headers": {"payment-required": "base64data"},
        }
        mock_execute.side_effect = PaymentFlowError("x402 crypto payments not yet supported")
        result = runner.invoke(app, ["pay", "https://api.test/x402"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert "x402" in data["error"].lower() or "not yet" in data["error"].lower()
