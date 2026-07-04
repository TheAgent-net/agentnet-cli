from __future__ import annotations

import typer

from ...marketplace.auth import die, get_client, output
from ...marketplace.client import PlatformError


def discover(
    query: str = typer.Argument(help="What you need — an agent capability or a skill"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
) -> None:
    """Discover agents and community skills matching a query."""
    client = get_client()
    try:
        result = client.discover_agents(query=query, limit=limit)
        output(result)
    except PlatformError as e:
        die(str(e))
