from __future__ import annotations

import os
from typing import Any

import typer

from ...infra.config import load_config
from ...marketplace.auth import die, output
from ...marketplace.client import PlatformClient, PlatformError
from ...marketplace.catalogs.claude_marketplace import ClaudeMarketplaceClient, ClaudeMarketplaceError
from ...marketplace.catalogs.clawhub import ClawHubClient, ClawHubError
from ...marketplace.skills.discovery import SkillDiscovery


SearchKind = str


def _platform_client() -> PlatformClient | None:
    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config() or {}
    if not token:
        token = config.get("api_token", "")
    if not token:
        return None

    platform_url = os.environ.get("AGENTNET_PLATFORM_URL", "") or config.get(
        "platform_url", "https://app.agentnet.market",
    )
    return PlatformClient(base_url=platform_url, api_token=token)


def _skill_search(query: str, limit: int) -> dict[str, Any]:
    config = load_config() or {}
    with SkillDiscovery(
        platform_url=config.get("platform_url"),
        api_token=config.get("api_token"),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
    ) as disco:
        return disco.discover(use_case=query, limit=limit)


def _plugin_search(query: str, limit: int, category: str | None) -> dict[str, Any]:
    errors: list[str] = []
    results: list[dict[str, Any]] = []

    try:
        with ClaudeMarketplaceClient() as client:
            data = client.search(query=query, limit=limit, category=category)
            for item in data.get("results", []):
                results.append({**item, "source": "claude-marketplace"})
    except ClaudeMarketplaceError as e:
        errors.append(f"claude-marketplace: {e}")

    try:
        with ClawHubClient() as client:
            data = client.search(query=query, limit=limit, category=category)
            for item in data.get("results", []):
                results.append({**item, "source": "clawhub"})
    except ClawHubError as e:
        errors.append(f"clawhub: {e}")

    return {
        "query": query,
        "source": "plugins",
        "total": len(results),
        "results": results[:limit],
        "errors": errors,
    }


def search(
    query: str = typer.Argument(help="What to search for"),
    kind: SearchKind = typer.Option(
        "all",
        "--type",
        "-t",
        help="Search type: all, marketplace, listings, agents, skills, or plugins",
    ),
    category: str | None = typer.Option(None, "--category", "-c", help="Category filter"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    max_price: int | None = typer.Option(None, "--max-price", help="Max price in USD"),
) -> None:
    """Search Agent-net across marketplace listings, agents, skills, and plugins."""
    if kind not in {"all", "marketplace", "listings", "agents", "skills", "plugins"}:
        die("Invalid --type. Use: all, marketplace, listings, agents, skills, or plugins.")

    if kind in {"skills", "plugins"}:
        try:
            result = _skill_search(query, limit) if kind == "skills" else _plugin_search(query, limit, category)
            output(result)
            return
        except Exception as e:
            die(str(e))

    client = _platform_client()
    if client is not None:
        try:
            result = client.search(
                query=query,
                kind=kind,
                category=category,
                limit=limit,
                max_price=max_price,
            )
            output(result)
            return
        except PlatformError as e:
            die(str(e))

    if kind == "all":
        result = {
            "query": query,
            "mode": "local",
            "note": "Marketplace search requires 'agentnet setup' or AGENTNET_TOKEN; returning local skills/plugins results.",
            "skills": _skill_search(query, limit),
            "plugins": _plugin_search(query, limit, category),
        }
        output(result)
        return

    die("Not authenticated. Run 'agentnet setup' or set AGENTNET_TOKEN.")
