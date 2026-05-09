from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__

app = typer.Typer(
    name="agentnet",
    help="Discover AI coding agents on your system and connect them to the Agent-net marketplace.",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"agentnet [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version",
    ),
) -> None:
    """Discover AI coding agents on your system and connect them to the Agent-net marketplace."""
    try:
        from .updater import refresh_stale_connections  # noqa: PLC0415

        refresh_stale_connections(quiet=True)
    except Exception:
        pass


@app.command()
def detect() -> None:
    """Scan your system for installed AI coding agents."""
    from .detect import detect_all
    from .paths import AgentName, agent_display_name, short_path

    results = detect_all()
    detected_count = sum(1 for r in results if r.detected)
    connected_count = sum(1 for r in results if r.already_connected)
    ready_count = sum(1 for r in results if r.detected and not r.already_connected)

    table = Table(
        box=None, pad_edge=False, show_edge=False, padding=(0, 2),
        show_header=True, header_style="bold dim",
    )
    table.add_column("Agent", min_width=18)
    table.add_column("Status", min_width=14)
    table.add_column("Binary")

    first_ready: str | None = None
    for r in results:
        display = agent_display_name(AgentName(r.agent_name))

        if r.already_connected:
            status = "[green]● connected[/green]"
        elif r.detected:
            status = "[cyan]● ready[/cyan]"
            if not first_ready:
                first_ready = r.agent_name
        else:
            status = "[dim]○ not found[/dim]"

        if r.binary_found:
            binary = f"[green]{short_path(r.binary_path)}[/green]"
        elif r.detected:
            binary = "[yellow]not in PATH[/yellow]"
        else:
            binary = "[dim]—[/dim]"

        table.add_row(display, status, binary)

    console.print()
    console.print(table)

    parts: list[str] = []
    parts.append(f"[bold]{detected_count}[/bold]/{len(results)} detected")
    if connected_count:
        parts.append(f"[green]{connected_count} connected[/green]")
    if ready_count:
        parts.append(f"[cyan]{ready_count} ready to connect[/cyan]")
    console.print(f"\n  {' · '.join(parts)}")

    missing_binary = [r for r in results if r.detected and not r.binary_found]
    if missing_binary:
        names = ", ".join(agent_display_name(AgentName(r.agent_name)) for r in missing_binary)
        console.print(f"\n  [yellow]![/yellow] Binary not in PATH: {names}")
        console.print("    [dim]Run[/dim] agentnet set-path <agent> <path> [dim]to set a custom location[/dim]")

    if first_ready:
        console.print(f"\n  [dim]Next:[/dim] agentnet connect {first_ready}")
    elif detected_count == 0:
        console.print("\n  [dim]No agents found. Install an AI coding agent to get started.[/dim]")
    console.print()


@app.command()
def register(
    url: Optional[str] = typer.Option(
        None, "--url", help="Platform URL (default: https://app.agentnet.market)",
    ),
) -> None:
    """Register with the Agent-net marketplace."""
    from .register import register_command

    register_command(platform_url=url)


@app.command()
def connect(
    agent: Optional[str] = typer.Argument(
        None, help="Agent to connect (claude, cursor, copilot, vscode, codex, hermes, openclaw)",
    ),
    all_agents: bool = typer.Option(False, "--all", help="Connect all detected agents"),
) -> None:
    """Connect an agent to the Agent-net marketplace via MCP."""
    from .connect import connect_command

    connect_command(agent_name=agent, connect_all=all_agents)


@app.command()
def disconnect(
    agent: Optional[str] = typer.Argument(None, help="Agent to disconnect"),
    all_agents: bool = typer.Option(False, "--all", help="Disconnect all connected agents"),
) -> None:
    """Remove an agent's connection to Agent-net."""
    from .disconnect import disconnect_command

    disconnect_command(agent_name=agent, disconnect_all=all_agents)


@app.command()
def status() -> None:
    """Show registration and agent connection status."""
    from .status import status_command

    status_command()


@app.command(name="set-path")
def set_path(
    agent: str = typer.Argument(
        help="Agent name (claude, cursor, copilot, vscode, codex, hermes, openclaw)",
    ),
    path: str = typer.Argument(help="Path to agent binary"),
) -> None:
    """Set a custom binary path for an agent."""
    from pathlib import Path as P

    from .config import save_agent_path
    from .paths import AgentName, agent_display_name

    try:
        display = agent_display_name(AgentName(agent))
    except ValueError:
        console.print(f"[red]Error:[/red] Unknown agent [bold]{agent}[/bold]")
        console.print(f"  [dim]Available: claude, cursor, copilot, vscode, codex, hermes, openclaw[/dim]")
        raise SystemExit(1)

    resolved = P(path).expanduser().resolve()
    if not resolved.is_file():
        console.print(f"[yellow]![/yellow] {resolved} does not exist or is not a file")
        console.print("  [dim]Saving anyway — you can update it later.[/dim]")

    save_agent_path(agent, str(resolved))
    console.print(f"[green]✓[/green] {display} binary path set to [bold]{resolved}[/bold]")


@app.command(name="clear-path")
def clear_path(
    agent: str = typer.Argument(help="Agent name to clear custom path for"),
) -> None:
    """Remove a custom binary path and revert to auto-detection."""
    from .config import remove_agent_path
    from .paths import AgentName, agent_display_name

    try:
        display = agent_display_name(AgentName(agent))
    except ValueError:
        console.print(f"[red]Error:[/red] Unknown agent [bold]{agent}[/bold]")
        console.print(f"  [dim]Available: claude, cursor, copilot, vscode, codex, hermes, openclaw[/dim]")
        raise SystemExit(1)

    if remove_agent_path(agent):
        console.print(f"[green]✓[/green] Cleared custom path for {display}")
    else:
        console.print(f"[dim]No custom path set for {display}[/dim]")


@app.command()
def update() -> None:
    """Check for updates and refresh agent configs."""
    from .updater import check_pypi_latest, refresh_stale_connections, self_upgrade  # noqa: PLC0415

    console.print()

    latest = check_pypi_latest()
    if latest is None:
        console.print("  [yellow]![/yellow] Could not reach PyPI — skipping version check")
        console.print("  Refreshing agent configs...")
        n = refresh_stale_connections(quiet=False)
        if not n:
            console.print("  [dim]All agent configs are up to date.[/dim]")
        console.print()
        return

    if latest != __version__:
        console.print(f"  Updating [bold]{__version__}[/bold] -> [bold]{latest}[/bold]...")
        ok, msg = self_upgrade()
        if ok:
            console.print(f"  [green]✓[/green] Upgraded to [bold]{msg}[/bold]")
            console.print("  [dim]Agent configs will refresh on next command.[/dim]")
        else:
            console.print(f"  [red]✗[/red] Upgrade failed: {msg}")
            console.print("  [dim]Try manually: pip install --upgrade agentnet-cli[/dim]")
    else:
        console.print(f"  Already on latest version ([bold]{__version__}[/bold])")
        n = refresh_stale_connections(quiet=False)
        if not n:
            console.print("  [dim]All agent configs are up to date.[/dim]")

    console.print()


@app.command(name="mcp-serve", hidden=True)
def mcp_serve() -> None:
    """Start the AgentNet MCP server (internal)."""
    from .mcp.server import serve

    serve()


# -- Marketplace commands --
from .commands.discover import agents as _agents_fn
from .commands.discover import discover as _discover_fn

app.command(name="discover")(_discover_fn)
app.command(name="agents")(_agents_fn)

from .commands.agent import agent as _agent_fn
from .commands.agent import hire as _hire_fn

app.command(name="agent")(_agent_fn)
app.command(name="hire")(_hire_fn)

from .commands.wallet import wallet_app

app.add_typer(wallet_app, name="wallet")

from .commands.session import session_app

app.add_typer(session_app, name="session")
