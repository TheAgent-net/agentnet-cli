"""Tests for pay CLI command."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from agentnet_cli.main import app

runner = CliRunner()


class TestPayCommand:
    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    @patch("agentnet_cli.commands.pay.LinkClient")
    @patch("agentnet_cli.commands.pay.SpendController")
    def test_pay_non_402_returns_directly(self, MockCtrl, MockLink, MockMpp, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": False,
            "status_code": 200,
            "body": {"data": "free"},
            "headers": {},
        }
        MockCtrl.return_value.check_allowed.return_value = True
        result = runner.invoke(app, ["pay", "https://api.test/free"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status_code"] == 200

    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    @patch("agentnet_cli.commands.pay.LinkClient")
    @patch("agentnet_cli.commands.pay.SpendController")
    def test_pay_402_mpp_full_lifecycle(self, MockCtrl, MockLink, MockMpp, fake_home):
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
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = True

        mock_link = MockLink.return_value
        mock_link.list_payment_methods.return_value = {"payment_methods": [{"id": "pm_test"}]}
        mock_link.mpp_decode.return_value = {"networkId": "net_1"}
        mock_link.spend_request_create.return_value = {"id": "lsrq_001"}
        mock_link.spend_request_approve.return_value = {"status": "pending_approval"}
        mock_link.spend_request_retrieve.return_value = {"status": "approved"}
        mock_link.mpp_pay.return_value = {
            "status": "success",
            "receipt_ref": "pi_abc",
        }

        result = runner.invoke(app, ["pay", "https://api.test/paid"])
        assert result.exit_code == 0

        mock_link.spend_request_create.assert_called_once()
        create_kwargs = mock_link.spend_request_create.call_args.kwargs
        assert create_kwargs["amount_cents"] == 150
        assert create_kwargs["credential_type"] == "shared_payment_token"

        mock_link.spend_request_approve.assert_called_once_with("lsrq_001")
        mock_link.spend_request_retrieve.assert_called_once()
        mock_link.mpp_pay.assert_called_once()

        pay_kwargs = mock_link.mpp_pay.call_args.kwargs
        assert pay_kwargs["spend_request_id"] == "lsrq_001"
        assert pay_kwargs["method"] == "GET"

    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    @patch("agentnet_cli.commands.pay.SpendController")
    def test_pay_rejects_over_max_amount(self, MockCtrl, MockMpp, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 5000},
            "headers": {"www-authenticate": 'Payment method="stripe"'},
        }
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = False
        result = runner.invoke(app, ["pay", "https://api.test/expensive"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert "exceed" in data["error"].lower() or "limit" in data["error"].lower()

    @patch("agentnet_cli.commands.pay.MppPaymentClient")
    @patch("agentnet_cli.commands.pay.SpendController")
    def test_x402_not_supported(self, MockCtrl, MockMpp, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 100},
            "headers": {"payment-required": "base64data"},
        }
        MockMpp.return_value.detect_protocol.return_value = "x402"
        MockCtrl.return_value.check_allowed.return_value = True
        result = runner.invoke(app, ["pay", "https://api.test/x402"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert "x402" in data["error"].lower() or "not yet" in data["error"].lower()
