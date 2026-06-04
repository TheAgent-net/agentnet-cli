from __future__ import annotations

from typing import Any

import httpx

from ..platform.client import PlatformClient
from ..plugins.claude_marketplace import ClaudeMarketplaceClient
from ..plugins.clawhub import ClawHubClient
from ..skills.client import SkillsClient
from ..skills.skillsmp import SkillsMPClient


class ToolHandlers:
    def __init__(
        self,
        *,
        platform_url: str,
        api_token: str,
        agent_id: str,
        http_client: httpx.Client | None = None,
        skills_http_client: httpx.Client | None = None,
        skillsmp_http_client: httpx.Client | None = None,
        claude_marketplace_http_client: httpx.Client | None = None,
        clawhub_http_client: httpx.Client | None = None,
    ) -> None:
        self._client = PlatformClient(
            base_url=platform_url,
            api_token=api_token,
            http_client=http_client or httpx.Client(timeout=30.0),
        )
        self._skills_client = SkillsClient(http_client=skills_http_client)
        self._skillsmp_client = SkillsMPClient(http_client=skillsmp_http_client)
        self._claude_marketplace = ClaudeMarketplaceClient(http_client=claude_marketplace_http_client)
        self._clawhub_client = ClawHubClient(http_client=clawhub_http_client)
        self._agent_id = agent_id

    def discover(
        self,
        *,
        query: str,
        category: str | None = None,
        max_results: int = 20,
        max_price: int | None = None,
    ) -> dict[str, Any]:
        return self._client.discover(
            query=query, category=category, max_results=max_results, max_price=max_price,
        )

    def discover_agents(self, *, query: str, limit: int = 20) -> dict[str, Any]:
        return self._client.discover_agents(query=query, limit=limit)

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        return self._client.get_agent(agent_id=agent_id)

    def use_agent(
        self, *, agent_id: str, task: str, max_amount: float = 0, quote_id: str | None = None,
    ) -> dict[str, Any]:
        if max_amount < 0 or max_amount > 1000:
            raise ValueError("max_amount must be between 0 and 1000")
        return self._client.use_agent(agent_id=agent_id, task=task, max_amount=max_amount, quote_id=quote_id)

    def continue_session(self, *, session_id: str, message: str) -> dict[str, Any]:
        return self._client.continue_session(session_id=session_id, message=message)

    def settle_session(self, *, session_id: str) -> dict[str, Any]:
        return self._client.settle_session(session_id=session_id)

    def wallet(self, *, action: str, limit: int = 50) -> dict[str, Any]:
        if action not in ("balance", "history"):
            raise ValueError("Invalid action: must be 'balance' or 'history'")
        if action == "balance":
            return self._client.wallet_balance(agent_id=self._agent_id)
        return self._client.wallet_history(agent_id=self._agent_id, limit=limit)

    def wallet_topup(self, *, amount: float) -> dict[str, Any]:
        if amount <= 0 or amount > 10000:
            raise ValueError("amount must be between 0 (exclusive) and 10000")
        return self._client.wallet_topup(agent_id=self._agent_id, amount=amount)

    def search_skills(
        self,
        *,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self._skills_client.search(query=query, limit=limit)

    def search_skillsmp(
        self,
        *,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "recent",
        category: str | None = None,
    ) -> dict[str, Any]:
        return self._skillsmp_client.search(
            query=query, limit=limit, page=page, sort_by=sort_by, category=category,
        )

    def search_claude_plugins(
        self,
        *,
        query: str,
        limit: int = 20,
        category: str | None = None,
    ) -> dict[str, Any]:
        return self._claude_marketplace.search(query=query, limit=limit, category=category)

    def search_clawhub(
        self,
        *,
        query: str,
        limit: int = 20,
        category: str | None = None,
        family: str | None = None,
    ) -> dict[str, Any]:
        return self._clawhub_client.search(
            query=query, limit=limit, category=category, family=family,
        )
