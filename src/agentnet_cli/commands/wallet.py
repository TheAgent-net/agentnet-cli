from __future__ import annotations

import typer

from ..marketplace import die, get_agent_id, get_client, output
from ..platform.client import PlatformError

wallet_app = typer.Typer(help="Manage your Agent-net wallet.")


@wallet_app.command()
def balance() -> None:
    """Check your current wallet balance."""
    client = get_client()
    aid = get_agent_id()
    try:
        result = client.wallet_balance(agent_id=aid)
        output(result)
    except PlatformError as e:
        die(str(e))


@wallet_app.command()
def history(
    limit: int = typer.Option(50, "--limit", "-l", help="Number of transactions to show"),
) -> None:
    """View recent wallet transactions."""
    client = get_client()
    aid = get_agent_id()
    try:
        result = client.wallet_history(agent_id=aid, limit=limit)
        output(result)
    except PlatformError as e:
        die(str(e))


@wallet_app.command()
def topup(
    amount: float = typer.Argument(help="Amount to add in USD"),
) -> None:
    """Add funds to your wallet."""
    client = get_client()
    aid = get_agent_id()
    try:
        result = client.wallet_topup(agent_id=aid, amount=amount)
        output(result)
    except PlatformError as e:
        die(str(e))
