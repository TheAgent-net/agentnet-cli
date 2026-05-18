"""Tests for shared MPP payment flow."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agentnet_cli.payments.mpp_flow import PaymentFlowError, execute_mpp_payment


def _probe_402(amount_minor=150):
    return {
        "requires_payment": True,
        "status_code": 402,
        "body": {
            "amount_minor": amount_minor,
            "agent_name": "TestBot",
            "description": "A test agent for payments",
        },
        "headers": {"www-authenticate": 'Payment id="x", method="stripe"'},
    }


class TestExecuteMppPayment:
    @patch("agentnet_cli.payments.mpp_flow.LinkClient")
    @patch("agentnet_cli.payments.mpp_flow.SpendController")
    @patch("agentnet_cli.payments.mpp_flow.MppPaymentClient")
    def test_full_lifecycle(self, MockMpp, MockCtrl, MockLink):
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = True

        mock_link = MockLink.return_value
        mock_link.list_payment_methods.return_value = {"payment_methods": [{"id": "pm_1"}]}
        mock_link.spend_request_create.return_value = {"id": "lsrq_001"}
        mock_link.spend_request_approve.return_value = {"status": "pending_approval"}
        mock_link.spend_request_retrieve.return_value = {"status": "approved"}
        mock_link.mpp_pay.return_value = {"status": "success", "receipt_ref": "pi_abc"}

        result = execute_mpp_payment(
            probe_result=_probe_402(),
            url="https://api.test/paid",
        )

        assert result["status"] == "success"
        mock_link.spend_request_create.assert_called_once()
        create_kwargs = mock_link.spend_request_create.call_args.kwargs
        assert create_kwargs["amount_cents"] == 150
        assert create_kwargs["credential_type"] == "shared_payment_token"
        mock_link.spend_request_approve.assert_called_once_with("lsrq_001")
        mock_link.mpp_pay.assert_called_once()

    @patch("agentnet_cli.payments.mpp_flow.SpendController")
    @patch("agentnet_cli.payments.mpp_flow.MppPaymentClient")
    def test_rejects_over_spend_limit(self, MockMpp, MockCtrl):
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = False

        with pytest.raises(PaymentFlowError, match="spend limit"):
            execute_mpp_payment(
                probe_result=_probe_402(amount_minor=99900),
                url="https://api.test/expensive",
            )

    @patch("agentnet_cli.payments.mpp_flow.SpendController")
    @patch("agentnet_cli.payments.mpp_flow.MppPaymentClient")
    def test_x402_not_supported(self, MockMpp, MockCtrl):
        MockMpp.return_value.detect_protocol.return_value = "x402"
        MockCtrl.return_value.check_allowed.return_value = True

        with pytest.raises(PaymentFlowError, match="x402"):
            execute_mpp_payment(
                probe_result=_probe_402(),
                url="https://api.test/x402",
            )

    @patch("agentnet_cli.payments.mpp_flow.LinkClient")
    @patch("agentnet_cli.payments.mpp_flow.SpendController")
    @patch("agentnet_cli.payments.mpp_flow.MppPaymentClient")
    def test_timeout_cancels_spend_request(self, MockMpp, MockCtrl, MockLink):
        from agentnet_cli.payments.link import LinkError

        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = True

        mock_link = MockLink.return_value
        mock_link.list_payment_methods.return_value = {"payment_methods": [{"id": "pm_1"}]}
        mock_link.spend_request_create.return_value = {"id": "lsrq_timeout"}
        mock_link.spend_request_approve.return_value = {"status": "pending_approval"}
        mock_link.spend_request_retrieve.side_effect = LinkError("timed out")

        with pytest.raises(PaymentFlowError, match="timed out"):
            execute_mpp_payment(
                probe_result=_probe_402(),
                url="https://api.test/slow",
            )

        mock_link.spend_request_cancel.assert_called_once_with("lsrq_timeout")

    @patch("agentnet_cli.payments.mpp_flow.LinkClient")
    @patch("agentnet_cli.payments.mpp_flow.SpendController")
    @patch("agentnet_cli.payments.mpp_flow.MppPaymentClient")
    def test_no_payment_methods_error(self, MockMpp, MockCtrl, MockLink):
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = True
        MockLink.return_value.list_payment_methods.return_value = {"payment_methods": []}

        with pytest.raises(PaymentFlowError, match="No Stripe Link"):
            execute_mpp_payment(
                probe_result=_probe_402(),
                url="https://api.test/paid",
            )

    @patch("agentnet_cli.payments.mpp_flow.LinkClient")
    @patch("agentnet_cli.payments.mpp_flow.SpendController")
    @patch("agentnet_cli.payments.mpp_flow.MppPaymentClient")
    def test_context_truncated_to_500(self, MockMpp, MockCtrl, MockLink):
        MockMpp.return_value.detect_protocol.return_value = "mpp"
        MockCtrl.return_value.check_allowed.return_value = True

        mock_link = MockLink.return_value
        mock_link.list_payment_methods.return_value = {"payment_methods": [{"id": "pm_1"}]}
        mock_link.spend_request_create.return_value = {"id": "lsrq_001"}
        mock_link.spend_request_approve.return_value = {}
        mock_link.spend_request_retrieve.return_value = {}
        mock_link.mpp_pay.return_value = {"status": "success", "receipt_ref": "pi_x"}

        probe = _probe_402()
        probe["body"]["description"] = "A" * 600

        execute_mpp_payment(probe_result=probe, url="https://api.test/long")

        ctx = mock_link.spend_request_create.call_args.kwargs["context"]
        assert len(ctx) <= 500
