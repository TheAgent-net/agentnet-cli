from __future__ import annotations

import typer

from ..marketplace import die, get_client, output
from ..platform.client import PlatformError


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


def hire(
    agent_id: str = typer.Argument(help="Agent to hire"),
    task: str = typer.Option(..., "--task", "-t", help="Task description"),
    budget: float = typer.Option(0, "--budget", "-b", help="Max budget in USD"),
) -> None:
    """Hire an agent to do a task. Returns result or session_id for follow-up."""
    client = get_client()
    try:
        result = client.use_agent(agent_id=agent_id, task=task, max_amount=budget)
        output(result)
    except PlatformError as e:
        die(str(e))
