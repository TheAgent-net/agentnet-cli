from __future__ import annotations

from typing import Optional

import typer

from ..marketplace import die, output
from ..payments.link import LinkClient, LinkError
from ..payments.mpp_client import MppPaymentClient
from ..payments.spend_controls import SpendController


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

    if protocol == "mpp" and "stripe" in str(probe_result.get("headers", {})):
        try:
            link = LinkClient()
            result = link.mpp_pay(url=url, spend_request_id="auto")
            ctrl.record_spend(amount_usd=amount_usd, receipt_ref="mpp_pay")
            output(result)
        except LinkError as e:
            die(f"Link payment failed: {e}")
    elif protocol == "x402":
        die("x402 crypto payments require a wallet. Use --prefer crypto (not yet supported)")
    else:
        die(f"Unknown payment protocol at {url}")
