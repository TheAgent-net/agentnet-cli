from __future__ import annotations

import sys
from typing import Optional

import typer

from ..marketplace import die, output
from ..payments.link import LinkClient, LinkError
from ..payments.mpp_client import MppPaymentClient
from ..payments.mpp_flow import PaymentFlowError, execute_mpp_payment


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

    www_auth = probe_result.get("headers", {}).get("www-authenticate", "")
    if www_auth:
        try:
            LinkClient().mpp_decode(www_auth)
        except LinkError as e:
            print(f"Warning: Failed to decode payment challenge: {e}", file=sys.stderr)

    header_list = [f"{k}: {v}" for k, v in probe_headers.items()] or None

    try:
        result = execute_mpp_payment(
            probe_result=probe_result,
            url=url,
            method=method,
            data=data,
            max_amount=max_amount,
            headers=header_list,
            via="marketplace",
        )
        output(result)
    except PaymentFlowError as e:
        die(str(e))
