from __future__ import annotations

import typer

from ...marketplace.auth import die, get_client, output
from ...marketplace.client import PlatformError


def agent(
    agent_id: str = typer.Argument(
        help="Agent or skill ID from discover results (skill IDs are prefixed skill:)",
    ),
) -> None:
    """Get full details about an agent or a community skill's full content."""
    client = get_client()
    try:
        if agent_id.startswith("skill:"):
            result = client.get_skill(skill_id=agent_id)
        else:
            result = client.get_agent(agent_id=agent_id)
        output(result)
    except PlatformError as e:
        die(str(e))
