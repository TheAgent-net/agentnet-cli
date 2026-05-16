from __future__ import annotations

import typer

from ..marketplace import die, output
from ..payments.link import LinkClient, LinkError

link_app = typer.Typer(help="Manage Stripe Link wallet connection.")


@link_app.command(name="auth")
def auth_login(
    client_name: str = typer.Option("agentnet", "--client-name", "-n", help="Agent name for Link"),
) -> None:
    """Connect your Stripe Link account (OAuth device flow)."""
    try:
        result = LinkClient().auth_login(client_name=client_name)
        output(result)
    except LinkError as e:
        die(str(e))


@link_app.command()
def status() -> None:
    """Show Link authentication status."""
    try:
        result = LinkClient().auth_status()
        output(result)
    except LinkError as e:
        die(str(e))


@link_app.command()
def methods() -> None:
    """List saved payment methods from Link wallet."""
    try:
        result = LinkClient().list_payment_methods()
        output(result)
    except LinkError as e:
        die(str(e))
