from __future__ import annotations

from typing import Any

import httpx


class ClawHubError(Exception):
    pass


class ClawHubClient:
    """Thin wrapper around the ClawHub public API (clawhub.ai)."""

    BASE_URL = "https://clawhub.ai"

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._http = http_client or httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ClawHubClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        from agentnet_cli import __version__  # noqa: PLC0415

        return {"User-Agent": f"agentnet-cli/{__version__}"}

    def _handle_response(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            status = resp.status_code
            if status == 429:
                raise ClawHubError("Rate limited — try again later") from None
            if 500 <= status < 600:
                raise ClawHubError("ClawHub server error") from None
            raise ClawHubError(f"Request failed ({status})") from None
        try:
            return resp.json()
        except ValueError:
            raise ClawHubError("Invalid response from ClawHub") from None

    def search(
        self,
        *,
        query: str,
        limit: int = 20,
        sort: str | None = None,
        category: str | None = None,
        family: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "limit": limit}
        if sort:
            params["sort"] = sort
        if category:
            params["category"] = category
        if family:
            params["family"] = family
        resp = self._http.get(
            f"{self.BASE_URL}/api/v1/search",
            headers=self._headers(),
            params=params,
        )
        return self._handle_response(resp)

    def browse(
        self,
        *,
        limit: int = 20,
        sort: str = "stars",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "sort": sort}
        resp = self._http.get(
            f"{self.BASE_URL}/api/v1/skills",
            headers=self._headers(),
            params=params,
        )
        return self._handle_response(resp)
