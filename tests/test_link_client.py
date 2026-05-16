"""Tests for Link CLI subprocess wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentnet_cli.payments.link import LinkClient, LinkError


class TestLinkAuthStatus:
    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_returns_authenticated(self, mock_run):
        mock_run.return_value = {"authenticated": True, "email": "user@test.com"}
        client = LinkClient()
        status = client.auth_status()
        assert status["authenticated"] is True
        assert status["email"] == "user@test.com"
        mock_run.assert_called_once_with(["auth", "status"])

    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_returns_not_authenticated(self, mock_run):
        mock_run.return_value = {"authenticated": False}
        client = LinkClient()
        status = client.auth_status()
        assert status["authenticated"] is False


class TestLinkAuthLogin:
    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_returns_verification_url(self, mock_run):
        mock_run.return_value = {
            "verification_url": "https://link.com/verify/abc",
            "user_code": "ABCD-1234",
        }
        client = LinkClient()
        result = client.auth_login(client_name="agentnet-test")
        assert result["verification_url"] == "https://link.com/verify/abc"
        mock_run.assert_called_once_with(
            ["auth", "login", "--client-name", "agentnet-test"],
        )


class TestLinkPaymentMethods:
    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_lists_methods(self, mock_run):
        mock_run.return_value = {
            "payment_methods": [
                {"id": "pm_1", "type": "card", "is_default": True},
            ],
        }
        client = LinkClient()
        methods = client.list_payment_methods()
        assert len(methods["payment_methods"]) == 1
        assert methods["payment_methods"][0]["id"] == "pm_1"


class TestLinkMppPay:
    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_pays_via_mpp(self, mock_run):
        mock_run.return_value = {
            "status": "success",
            "receipt": {"receipt_ref": "pi_abc123"},
        }
        client = LinkClient()
        result = client.mpp_pay(
            url="https://api.example.com/paid",
            spend_request_id="sr_xyz",
        )
        assert result["status"] == "success"
        mock_run.assert_called_once_with(
            ["mpp", "pay", "https://api.example.com/paid",
             "--spend-request-id", "sr_xyz"],
        )


class TestRunLinkCli:
    @patch("agentnet_cli.payments.link.subprocess.run")
    def test_parses_json_output(self, mock_subprocess):
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='{"ok": true}\n',
            stderr="",
        )
        from agentnet_cli.payments.link import _run_link_cli

        result = _run_link_cli(["auth", "status"])
        assert result == {"ok": True}
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "npx"
        assert "@stripe/link-cli" in call_args

    @patch("agentnet_cli.payments.link.subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_subprocess):
        mock_subprocess.return_value = MagicMock(
            returncode=1,
            stdout='{"error": "not authenticated"}\n',
            stderr="",
        )
        from agentnet_cli.payments.link import _run_link_cli

        with pytest.raises(LinkError, match="not authenticated"):
            _run_link_cli(["auth", "status"])
