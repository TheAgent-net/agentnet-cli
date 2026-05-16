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
    def test_pay_402_mpp_with_link(self, MockCtrl, MockLink, MockMpp, fake_home):
        MockMpp.return_value.probe.return_value = {
            "requires_payment": True,
            "status_code": 402,
            "body": {"amount_minor": 100, "accepted_methods": ["stripe"]},
            "headers": {"www-authenticate": 'Payment method="stripe"'},
        }
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = True
        MockLink.return_value.mpp_pay.return_value = {
            "status": "success",
            "body": {"result": "paid resource"},
        }
        result = runner.invoke(app, ["pay", "https://api.test/paid"])
        assert result.exit_code == 0
        MockLink.return_value.mpp_pay.assert_called_once()

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
