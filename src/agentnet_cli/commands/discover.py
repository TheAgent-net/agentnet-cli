from __future__ import annotations

import typer

from ..marketplace import die, get_client, output
from ..platform.client import PlatformError


def discover(
    query: str = typer.Argument(help="What to search for"),
    category: str | None = typer.Option(None, help="Filter by category"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    max_price: int | None = typer.Option(None, "--max-price", help="Max price in USD"),
) -> None:
    """Search the Agent-net marketplace for products and services."""
    client = get_client()
    try:
        result = client.discover(query=query, category=category, max_results=limit, max_price=max_price)
        output(result)
    except PlatformError as e:
        die(str(e))


def agents(
    query: str = typer.Argument(help="Agent name or capability to search for"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
) -> None:
    """Search for AI agents by name or capability."""
    client = get_client()
    try:
        result = client.discover_agents(query=query, limit=limit)
        output(result)
    except PlatformError as e:
        die(str(e))
