from __future__ import annotations

from typing import Any

import httpx


class SkillsError(Exception):
    pass


class SkillsClient:
    """Thin wrapper around the SkillsMP public API (skillsmp.com)."""

    BASE_URL = "https://skillsmp.com"

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._http = http_client or httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SkillsClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        from .. import __version__  # noqa: PLC0415

        return {"User-Agent": f"agentnet-cli/{__version__}"}

    def _handle_response(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            status = resp.status_code
            if status == 429:
                raise SkillsError("Rate limited — try again later") from None
            if 500 <= status < 600:
                raise SkillsError("SkillsMP server error") from None
            raise SkillsError(f"Request failed ({status})") from None
        try:
            return resp.json()
        except ValueError:
            raise SkillsError("Invalid response from SkillsMP") from None

    def search(
        self,
        *,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "recent",
        category: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": query,
            "limit": limit,
            "page": page,
            "sortBy": sort_by,
        }
        if category:
            params["category"] = category
        resp = self._http.get(
            f"{self.BASE_URL}/api/v1/skills/search",
            headers=self._headers(),
            params=params,
        )
        return self._handle_response(resp)
