from __future__ import annotations

import typer

from ...marketplace.auth import die, get_client, output
from ...marketplace.client import PlatformError


def agent(
    agent_id: str = typer.Argument(help="Agent ID from discovery results"),
) -> None:
    """Get full details about an agent — skills, pricing, trust score."""
    client = get_client()
    try:
        result = client.get_agent(agent_id=agent_id)
        output(result)
    except PlatformError as e:
        die(str(e))
