from __future__ import annotations

import json
import subprocess
from typing import Any


class LinkError(Exception):
    pass


def _run_link_cli(args: list[str]) -> dict[str, Any]:
    cmd = ["npx", "@stripe/link-cli", *args, "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
        method: str | None = None,
        data: str | None = None,
        headers: list[str] | None = None,
    ) -> dict[str, Any]:
        args = ["mpp", "pay", url, "--spend-request-id", spend_request_id]
        if method:
            args.extend(["--method", method])
        if data:
            args.extend(["--data", data])
        for h in headers or []:
            args.extend(["--header", h])
        args.extend(self._base_args())
        return _run_link_cli(args)
