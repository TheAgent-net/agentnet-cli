"""Tool actions for MCP and Hermes. All HTTP goes through PlatformClient."""

from __future__ import annotations

from typing import Any

import httpx

from ..marketplace.client import PlatformClient


class ToolActions:
    """Run marketplace tool actions through :class:`PlatformClient`."""

    def __init__(
        self,
        *,
        platform_url: str,
        api_token: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = PlatformClient(
            base_url=platform_url,
            api_token=api_token,
            http_client=http_client or httpx.Client(timeout=30.0),
        )

    def close(self) -> None:
        """Close the platform client."""
        self._client.close()

    def __enter__(self) -> ToolActions:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def search(
        self,
        *,
        query: str,
        type: str = "all",  # noqa: A002
        category: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search Agent-net for agents, skills, plugins, and listings."""
        return self._client.search(
            query=query,
            kind=type,
            category=category,
            limit=limit,
        )
