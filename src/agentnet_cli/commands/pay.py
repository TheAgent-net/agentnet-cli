from __future__ import annotations

from typing import Optional

import typer

from ..marketplace import die, output
from ..payments.link import LinkClient, LinkError
from ..payments.mpp_client import MppPaymentClient
from ..payments.spend_controls import SpendController


def _build_context(amount_usd: float, agent_name: str, description: str, url: str) -> str:
    ctx = f"Payment of ${amount_usd:.2f} to {agent_name} ({description}) via AgentNet marketplace at {url}"
    if len(ctx) < 100:
        ctx = ctx + " " + description[:100]
    return ctx[:500]


def pay(
    url: str = typer.Argument(help="URL of the service to pay"),
    method: str = typer.Option("GET", "--method", "-X", help="HTTP method"),
    data: Optional[str] = typer.Option(None, "--data", "-d", help="Request body"),
    header: Optional[list[str]] = typer.Option(None, "--header", "-H", help="Extra headers"),
    max_amount: float = typer.Option(25.0, "--max-amount", help="Max USD to spend"),
    prefer: str = typer.Option("stripe", "--prefer", help="Preferred payment method"),
) -> None:
    """Pay any MPP/x402-enabled service. Auto-detects protocol and handles payment."""
    mpp = MppPaymentClient()
    ctrl = SpendController(single_tx_limit_usd=max_amount)

    probe_headers: dict[str, str] = {}
    for h in header or []:
        if ":" in h:
            k, _, v = h.partition(":")
            probe_headers[k.strip()] = v.strip()

    try:
        probe_result = mpp.probe(url, method=method, data=data, headers=probe_headers)
    except Exception as e:
        die(f"Failed to reach {url}: {e}")

    if not probe_result["requires_payment"]:
        output(probe_result)
        return

    body = probe_result.get("body", {})
    amount_minor = body.get("amount_minor", 0) if isinstance(body, dict) else 0
    amount_usd = amount_minor / 100.0

    if not ctrl.check_allowed(amount_usd=amount_usd):
        die(f"Payment of ${amount_usd:.2f} exceeds spend limit (max ${max_amount:.2f})")

    protocol = mpp.detect_protocol(probe_result.get("headers", {}))

    if protocol == "x402":
        die("x402 crypto payments not yet supported via CLI. Use an x402-compatible wallet.")

    if protocol != "mpp":
        die(f"Unknown payment protocol at {url}")

    try:
        link = LinkClient()

        methods_resp = link.list_payment_methods()
        pm_list = methods_resp if isinstance(methods_resp, list) else methods_resp.get("data", methods_resp.get("payment_methods", []))
        if not pm_list:
            die("No Stripe Link payment methods found. Run 'agentnet link auth' first.")
        payment_method_id = pm_list[0].get("id", pm_list[0].get("payment_method_id", ""))

        www_auth = probe_result.get("headers", {}).get("www-authenticate", "")
        try:
            decoded = link.mpp_decode(www_auth)
        except LinkError:
            decoded = {}

        agent_name = body.get("agent_name", "Unknown") if isinstance(body, dict) else "Unknown"
        description = body.get("description", "") if isinstance(body, dict) else ""
        context = _build_context(amount_usd, agent_name, description, url)

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
        link.spend_request_retrieve(spend_request_id, interval=5, max_attempts=60)

        header_list = [f"{k}: {v}" for k, v in probe_headers.items()]
        result = link.mpp_pay(
            url=url,
            spend_request_id=spend_request_id,
            method=method,
            data=data or "{}",
            headers=header_list or None,
        )

        ctrl.record_spend(amount_usd=amount_usd, receipt_ref=result.get("receipt_ref", "mpp_pay"))
        output(result)

    except LinkError as e:
        die(f"Link payment failed: {e}")
