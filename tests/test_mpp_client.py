"""Tests for MPP 402 payment client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentnet_cli.payments.mpp_client import MppPaymentClient


def _mock_response(status_code, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.text = ""
    return resp


class TestProbeFor402:
    @patch("agentnet_cli.payments.mpp_client.httpx.Client")
    def test_detects_402_with_challenge(self, MockClient):
        client_inst = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=client_inst)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        client_inst.request.return_value = _mock_response(
            402,
            json_data={"error": "payment_required", "amount_minor": 100},
            headers={"www-authenticate": 'Payment method="stripe", intent="charge"'},
        )

        mpp = MppPaymentClient()
        result = mpp.probe("https://api.test/resource")
        assert result["requires_payment"] is True
        assert result["status_code"] == 402

    @patch("agentnet_cli.payments.mpp_client.httpx.Client")
    def test_returns_200_directly(self, MockClient):
        client_inst = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=client_inst)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        client_inst.request.return_value = _mock_response(
            200, json_data={"data": "free resource"},
        )

        mpp = MppPaymentClient()
        result = mpp.probe("https://api.test/free")
        assert result["requires_payment"] is False
        assert result["status_code"] == 200


class TestDetectProtocol:
    def test_detects_mpp_from_www_authenticate(self):
        mpp = MppPaymentClient()
        headers = {"www-authenticate": 'Payment method="stripe", intent="charge"'}
        assert mpp.detect_protocol(headers) == "mpp"

    def test_detects_x402_from_payment_required_header(self):
        mpp = MppPaymentClient()
        headers = {"payment-required": "eyJ4NDAyVmVyc2lvbiI6Mn0="}
        assert mpp.detect_protocol(headers) == "x402"

    def test_returns_unknown_for_bare_402(self):
        mpp = MppPaymentClient()
        assert mpp.detect_protocol({}) == "unknown"
