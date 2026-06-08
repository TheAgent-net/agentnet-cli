from __future__ import annotations

from typing import Any

import httpx


class ClaudeMarketplaceError(Exception):
    pass


class ClaudeMarketplaceClient:
    """Search the Claude Code plugin marketplace (static catalog from GitHub)."""

    CATALOG_URL = (
        "https://raw.githubusercontent.com/anthropics/claude-plugins-official"
        "/main/.claude-plugin/marketplace.json"
    )

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._http = http_client or httpx.Client(timeout=30.0)
        self._cache: list[dict[str, Any]] | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ClaudeMarketplaceClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        from agentnet_cli import __version__  # noqa: PLC0415

        return {"User-Agent": f"agentnet-cli/{__version__}"}

    def _fetch_catalog(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        try:
            resp = self._http.get(self.CATALOG_URL, headers=self._headers())
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            status = resp.status_code
            if status == 429:
                raise ClaudeMarketplaceError("Rate limited — try again later") from None
            if 500 <= status < 600:
                raise ClaudeMarketplaceError("GitHub server error") from None
            raise ClaudeMarketplaceError(f"Request failed ({status})") from None
        except httpx.TransportError as exc:
            raise ClaudeMarketplaceError(f"Network error: {exc}") from None
        try:
            data = resp.json()
        except ValueError:
            raise ClaudeMarketplaceError("Invalid response from GitHub") from None
        self._cache = data.get("plugins", [])
        return self._cache

    def search(
        self,
        *,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        plugins = self._fetch_catalog()
        q = query.lower()
        matches = []
        for p in plugins:
            if category and p.get("category", "") != category:
                continue
            name = p.get("name", "").lower()
            desc = p.get("description", "").lower()
            keywords = " ".join(p.get("keywords", [])).lower()
            author = (p.get("author") or {}).get("name", "").lower()
            if q in name or q in desc or q in keywords or q in author:
                matches.append({
                    "name": p.get("name"),
                    "description": p.get("description", ""),
                    "category": p.get("category", ""),
                    "author": (p.get("author") or {}).get("name", ""),
                    "homepage": p.get("homepage", ""),
                })
        return {
            "results": matches[:limit],
            "total": len(matches),
            "source": "claude-plugins-official",
        }
