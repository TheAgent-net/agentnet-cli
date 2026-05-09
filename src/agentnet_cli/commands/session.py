from __future__ import annotations

import typer

from ..marketplace import die, get_client, output
from ..platform.client import PlatformError

session_app = typer.Typer(help="Manage multi-turn agent sessions.")


@session_app.command(name="continue")
def continue_session(
    session_id: str = typer.Argument(help="Session ID from a previous hire"),
    message: str = typer.Option(..., "--message", "-m", help="Follow-up message"),
) -> None:
    """Send a follow-up message in a multi-turn session."""
    client = get_client()
    try:
        result = client.continue_session(session_id=session_id, message=message)
        output(result)
    except PlatformError as e:
        die(str(e))


@session_app.command()
def settle(
    session_id: str = typer.Argument(help="Session ID to settle"),
) -> None:
    """Confirm satisfaction and release payment for a session."""
    client = get_client()
    try:
        result = client.settle_session(session_id=session_id)
        output(result)
    except PlatformError as e:
        die(str(e))
