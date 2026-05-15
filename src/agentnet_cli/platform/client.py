from __future__ import annotations

import re
from typing import Any

import httpx


class PlatformError(Exception):
    pass


def _validate_path_segment(value: str) -> None:
    """Reject values that could cause path traversal or injection."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise PlatformError(f"Invalid identifier: {value!r}")


class PlatformClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str = "",
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = api_token
        self._http = http_client or httpx.Client(timeout=30.0)

    # -- context manager & cleanup (L-4) --

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PlatformClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- internal helpers --

    def _headers(self) -> dict[str, str]:
        from .. import __version__  # noqa: PLC0415

        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": f"agentnet-cli/{__version__}",
        }

    def _handle_response(self, resp: httpx.Response) -> dict[str, Any]:
        """Raise PlatformError on HTTP errors; safely parse JSON (H-11)."""
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            status = resp.status_code
            if status in (401, 403):
                raise PlatformError("Authentication failed") from None
            if status == 429:
                raise PlatformError("Rate limited, try again later") from None
            if 500 <= status < 600:
                raise PlatformError("Platform server error") from None
            raise PlatformError(f"Request failed ({status})") from None
        try:
            return resp.json()
        except ValueError:
            raise PlatformError("Invalid response from platform") from None

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._http.get(f"{self._base}{path}", headers=self._headers(), params=params)
        return self._handle_response(resp)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.post(f"{self._base}{path}", headers=self._headers(), json=body)
        return self._handle_response(resp)

    def _public_headers(self) -> dict[str, str]:
        from .. import __version__  # noqa: PLC0415

        return {
            "Content-Type": "application/json",
            "User-Agent": f"agentnet-cli/{__version__}",
        }

    def _public_post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._http.post(
            f"{self._base}{path}",
            headers=self._public_headers(),
            json=body or {},
        )
        return self._handle_response(resp)

    def _public_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._http.get(
            f"{self._base}{path}",
            headers=self._public_headers(),
            params=params,
        )
        return self._handle_response(resp)

    def cli_login_start(self) -> dict[str, Any]:
        return self._public_post("/auth/cli/login/start")

    def cli_login_poll(self, *, login_id: str, poll_secret: str) -> dict[str, Any]:
        _validate_path_segment(login_id)
        return self._public_get(
            f"/auth/cli/login/{login_id}",
            {"poll_secret": poll_secret},
        )

    def discover(self, *, query: str, category: str | None = None, max_results: int = 5, max_price: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "limit": max_results}
        if category:
            params["category"] = category
        if max_price is not None:
            params["max_price"] = max_price
        return self._get("/discover/listings", params)

    def discover_agents(self, *, query: str, limit: int = 20) -> dict[str, Any]:
        return self._get("/discover/", {"q": query, "limit": limit})

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        _validate_path_segment(agent_id)
        return self._get(f"/agents/{agent_id}")

    def list_agents(self) -> dict[str, Any]:
        return self._get("/agents/")

    def use_agent(self, *, agent_id: str, task: str, quote_id: str | None = None, max_amount: float = 0) -> dict[str, Any]:
        _validate_path_segment(agent_id)
        body: dict[str, Any] = {"message": task, "amount": max_amount}
        return self._post(f"/agents/{agent_id}/use", body)

    def continue_session(self, *, session_id: str, message: str) -> dict[str, Any]:
        return self._post(f"/agents/sessions/{session_id}/continue", {"message": message})

    def settle_session(self, *, session_id: str) -> dict[str, Any]:
        return self._post(f"/agents/sessions/{session_id}/settle", {})

    def wallet_balance(self, *, agent_id: str) -> dict[str, Any]:
        _validate_path_segment(agent_id)
        return self._get(f"/wallet/{agent_id}")

    def wallet_history(self, *, agent_id: str, limit: int = 50) -> dict[str, Any]:
        _validate_path_segment(agent_id)
        return self._get(f"/wallet/{agent_id}/history", {"limit": limit})

    def wallet_topup(self, *, agent_id: str, amount: float) -> dict[str, Any]:
        _validate_path_segment(agent_id)
        return self._post(f"/wallet/{agent_id}/topup", {"amount": amount})

    def verify_token(self) -> dict[str, Any]:
        return self._get("/auth/me")

    def token_info(self) -> dict[str, Any]:
        return self._get("/auth/token-info")

    def cli_register_agent(
        self, *, name: str, visibility: str = "private", description: str = "", url: str = "", tags: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "visibility": visibility, "description": description}
        if url:
            body["url"] = url
        if tags:
            body["tags"] = tags
        return self._post("/auth/cli/register-agent", body)
