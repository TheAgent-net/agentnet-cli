"""Shared MPP payment flow used by both CLI pay command and MCP tool."""
from __future__ import annotations

from typing import Any

from .link import LinkClient, LinkError
from .mpp_client import MppPaymentClient
from .spend_controls import SpendController


class PaymentFlowError(Exception):
    pass


def _build_context(amount_usd: float, agent_name: str, description: str, url: str, via: str) -> str:
    ctx = f"Payment of ${amount_usd:.2f} to {agent_name} ({description}) via AgentNet {via} at {url}"
    if len(ctx) < 100:
        ctx = ctx + " " + description[:100]
    return ctx[:500]


def execute_mpp_payment(
    *,
    probe_result: dict[str, Any],
    url: str,
    method: str = "GET",
    data: str | None = None,
    max_amount: float = 25.0,
    headers: list[str] | None = None,
    via: str = "marketplace",
) -> dict[str, Any]:
    """Run the full MPP spend-request lifecycle.

    Raises PaymentFlowError on any failure (spend limit, unsupported protocol,
    timeout, missing payment methods, etc.).
    """
    mpp = MppPaymentClient()
    ctrl = SpendController(single_tx_limit_usd=max_amount)

    body = probe_result.get("body", {})
    amount_minor = body.get("amount_minor", 0) if isinstance(body, dict) else 0
    amount_usd = amount_minor / 100.0

    if not ctrl.check_allowed(amount_usd=amount_usd):
        raise PaymentFlowError(
            f"Payment of ${amount_usd:.2f} exceeds spend limit (max ${max_amount:.2f})"
        )

    protocol = mpp.detect_protocol(probe_result.get("headers", {}))

    if protocol == "x402":
        raise PaymentFlowError("x402 crypto payments not yet supported")

    if protocol != "mpp":
        raise PaymentFlowError(f"Unsupported payment protocol: {protocol}")

    link = LinkClient()
    spend_request_id = None

    try:
        methods_resp = link.list_payment_methods()
        pm_list = (
            methods_resp if isinstance(methods_resp, list)
            else methods_resp.get("data", methods_resp.get("payment_methods", []))
        )
        if not pm_list:
            raise PaymentFlowError("No Stripe Link payment methods found. Run link auth first.")
        payment_method_id = pm_list[0].get("id", pm_list[0].get("payment_method_id", ""))

        agent_name = body.get("agent_name", "Unknown") if isinstance(body, dict) else "Unknown"
        description = body.get("description", "") if isinstance(body, dict) else ""
        context = _build_context(amount_usd, agent_name, description, url, via)

        sr = link.spend_request_create(
            amount_cents=amount_minor,
            merchant_name=agent_name,
            merchant_url=url,
            context=context,
            payment_method_id=payment_method_id,
            credential_type="shared_payment_token",
        )
        spend_request_id = sr.get("id", sr.get("spend_request_id", ""))

        link.spend_request_approve(spend_request_id)

        try:
            link.spend_request_retrieve(spend_request_id, interval=5, max_attempts=60)
        except LinkError as e:
            _cancel_spend_request(link, spend_request_id)
            raise PaymentFlowError(f"Payment approval timed out: {e}") from e

        result = link.mpp_pay(
            url=url,
            spend_request_id=spend_request_id,
            method=method,
            data=data or "{}",
            headers=headers,
        )

        ctrl.record_spend(amount_usd=amount_usd, receipt_ref=result.get("receipt_ref", "mpp_pay"))
        return result

    except LinkError as e:
        _cancel_spend_request(link, spend_request_id)
        raise PaymentFlowError(f"Link payment failed: {e}") from e


def _cancel_spend_request(link: LinkClient, spend_request_id: str | None) -> None:
    if not spend_request_id:
        return
    try:
        link.spend_request_cancel(spend_request_id)
    except LinkError:
        pass
