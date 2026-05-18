from __future__ import annotations

import json
import subprocess
from typing import Any


class LinkError(Exception):
    pass


def _run_link_cli(args: list[str]) -> dict[str, Any]:
    cmd = ["npx", "@stripe/link-cli", *args, "--format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise LinkError("npx not found — install Node.js to use Stripe Link")
    except subprocess.TimeoutExpired:
        raise LinkError("Link CLI timed out after 120s")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {}
    if result.returncode != 0:
        msg = data.get("error", result.stderr or f"link-cli exited {result.returncode}")
        raise LinkError(msg)
    return data


class LinkClient:
    def __init__(self, *, auth_file: str | None = None) -> None:
        self._auth_file = auth_file

    def _base_args(self) -> list[str]:
        if self._auth_file:
            return ["--auth", self._auth_file]
        return []

    def auth_login(self, *, client_name: str) -> dict[str, Any]:
        return _run_link_cli(
            ["auth", "login", "--client-name", client_name, *self._base_args()],
        )

    def auth_status(self) -> dict[str, Any]:
        return _run_link_cli(["auth", "status", *self._base_args()])

    def list_payment_methods(self) -> dict[str, Any]:
        return _run_link_cli(["payment-methods", "list", *self._base_args()])

    def mpp_pay(
        self,
        *,
        url: str,
        spend_request_id: str,
        method: str = "GET",
        data: str = "{}",
        headers: list[str] | None = None,
    ) -> dict[str, Any]:
        args = [
            "mpp", "pay", url,
            "--spend-request-id", spend_request_id,
            "--method", method,
            "--data", data,
        ]
        for h in headers or []:
            args.extend(["--header", h])
        args.extend(self._base_args())
        return _run_link_cli(args)

    def mpp_decode(self, www_authenticate: str) -> dict[str, Any]:
        return _run_link_cli(["mpp", "decode", www_authenticate, *self._base_args()])

    def spend_request_create(
        self,
        *,
        amount_cents: int,
        merchant_name: str,
        merchant_url: str,
        context: str,
        payment_method_id: str,
        credential_type: str = "shared_payment_token",
    ) -> dict[str, Any]:
        return _run_link_cli([
            "spend-request", "create",
            "--amount", str(amount_cents),
            "--merchant-name", merchant_name,
            "--merchant-url", merchant_url,
            "--context", context,
            "--payment-method-id", payment_method_id,
            "--credential-type", credential_type,
            *self._base_args(),
        ])

    def spend_request_approve(self, spend_request_id: str) -> dict[str, Any]:
        return _run_link_cli([
            "spend-request", "request-approval", spend_request_id,
            *self._base_args(),
        ])

    def spend_request_retrieve(
        self,
        spend_request_id: str,
        *,
        interval: int = 5,
        max_attempts: int = 60,
        include_card: bool = False,
    ) -> dict[str, Any]:
        args = [
            "spend-request", "retrieve", spend_request_id,
            "--interval", str(interval),
            "--max-attempts", str(max_attempts),
        ]
        if include_card:
            args.extend(["--include", "card"])
        args.extend(self._base_args())
        return _run_link_cli(args)

    def spend_request_cancel(self, spend_request_id: str) -> dict[str, Any]:
        return _run_link_cli([
            "spend-request", "cancel", spend_request_id,
            *self._base_args(),
        ])
