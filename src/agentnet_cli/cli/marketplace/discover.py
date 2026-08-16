from __future__ import annotations

import typer

from ...marketplace.auth import die, get_client, output
from ...marketplace.client import PlatformError


def discover(
    query: str = typer.Argument(help="What you need: an agent capability or a skill"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
) -> None:
    """Search Agent-net for agents, skills, and listings that match a query."""
    client = get_client()
    try:
        result = client.search(query=query, kind="all", limit=limit)
        output(result)
    except PlatformError as e:
        die(str(e))
