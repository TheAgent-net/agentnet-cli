from __future__ import annotations

import base64
import json
from typing import Any

import httpx


class MppPaymentError(Exception):
    pass


class MppPaymentClient:
    def probe(
        self,
        url: str,
        *,
        method: str = "GET",
        data: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        req_headers = dict(headers or {})
        if data and "content-type" not in {k.lower() for k in req_headers}:
            req_headers["Content-Type"] = "application/json"
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(
                method,
                url,
                content=data.encode() if data else None,
                headers=req_headers,
            )
        result: dict[str, Any] = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
        }
        try:
            result["body"] = resp.json()
        except Exception:
            result["body"] = resp.text
        result["requires_payment"] = resp.status_code == 402

        lower_headers = {k.lower(): v for k, v in resp.headers.items()}
        if "payment-response" in lower_headers:
            try:
                raw = lower_headers["payment-response"]
                result["x402_receipt"] = json.loads(base64.b64decode(raw))
            except Exception:
                result["x402_receipt"] = None

        return result

    def detect_protocol(self, headers: dict[str, str]) -> str:
        lower_headers = {k.lower(): v for k, v in headers.items()}
        if "www-authenticate" in lower_headers:
            auth = lower_headers["www-authenticate"].strip()
            if auth.lower().startswith("payment ") or auth.lower() == "payment":
                return "mpp"
        if "payment-required" in lower_headers:
            return "x402"
        return "unknown"
