"""Tests for Link CLI subprocess wrapper."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agentnet_cli.payments.link import LinkClient, LinkError, _run_link_cli


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
    def test_pays_via_mpp_with_required_args(self, mock_run):
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
        args = mock_run.call_args[0][0]
        assert "--method" in args
        assert args[args.index("--method") + 1] == "GET"
        assert "--data" in args
        assert args[args.index("--data") + 1] == "{}"

    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_passes_custom_method_and_data(self, mock_run):
        mock_run.return_value = {"status": "success"}
        client = LinkClient()
        client.mpp_pay(
            url="http://test",
            spend_request_id="sr_1",
            method="POST",
            data='{"message": "hi"}',
        )
        args = mock_run.call_args[0][0]
        assert args[args.index("--method") + 1] == "POST"
        assert args[args.index("--data") + 1] == '{"message": "hi"}'


class TestLinkMppDecode:
    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_decodes_www_authenticate(self, mock_run):
        mock_run.return_value = {"networkId": "net_1", "method": "stripe"}
        client = LinkClient()
        result = client.mpp_decode('Payment id="x", method="stripe"')
        assert result["networkId"] == "net_1"


class TestSpendRequestLifecycle:
    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_create(self, mock_run):
        mock_run.return_value = {"id": "lsrq_001"}
        client = LinkClient()
        result = client.spend_request_create(
            amount_cents=150,
            merchant_name="TestBot",
            merchant_url="http://test",
            context="Payment of $1.50",
            payment_method_id="pm_1",
        )
        assert result["id"] == "lsrq_001"
        args = mock_run.call_args[0][0]
        assert args[0:2] == ["spend-request", "create"]
        assert "--credential-type" in args
        assert args[args.index("--credential-type") + 1] == "shared_payment_token"

    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_approve(self, mock_run):
        mock_run.return_value = {"status": "pending_approval"}
        client = LinkClient()
        result = client.spend_request_approve("lsrq_001")
        assert result["status"] == "pending_approval"
        args = mock_run.call_args[0][0]
        assert args[0:2] == ["spend-request", "request-approval"]
        assert "lsrq_001" in args

    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_retrieve(self, mock_run):
        mock_run.return_value = {"status": "approved"}
        client = LinkClient()
        result = client.spend_request_retrieve("lsrq_001", interval=3, max_attempts=10)
        assert result["status"] == "approved"
        args = mock_run.call_args[0][0]
        assert "--interval" in args
        assert args[args.index("--interval") + 1] == "3"

    @patch("agentnet_cli.payments.link._run_link_cli")
    def test_cancel(self, mock_run):
        mock_run.return_value = {"status": "cancelled"}
        client = LinkClient()
        result = client.spend_request_cancel("lsrq_001")
        assert result["status"] == "cancelled"


class TestRunLinkCli:
    @patch("agentnet_cli.payments.link.subprocess.run")
    def test_parses_json_output(self, mock_subprocess):
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='{"ok": true}\n',
            stderr="",
        )
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
        with pytest.raises(LinkError, match="not authenticated"):
            _run_link_cli(["auth", "status"])

    @patch("agentnet_cli.payments.link.subprocess.run", side_effect=FileNotFoundError)
    def test_raises_on_npx_not_found(self, _mock_run):
        with pytest.raises(LinkError, match="npx not found"):
            _run_link_cli(["auth", "status"])

    @patch(
        "agentnet_cli.payments.link.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="x", timeout=120),
    )
    def test_raises_on_timeout(self, _mock_run):
        with pytest.raises(LinkError, match="timed out"):
            _run_link_cli(["mpp", "pay", "http://test"])
