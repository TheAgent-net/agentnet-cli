from __future__ import annotations

import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from agentnet_cli import __version__
from agentnet_cli.infra.platform import LOCAL_DEV_PLATFORM_URL, PRODUCTION_PLATFORM_URL

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
    dev: bool = typer.Option(
        False,
        "--dev",
        help=f"Use local platform ({LOCAL_DEV_PLATFORM_URL}) for this session",
    ),
) -> None:
    """Discover AI coding agents on your system and connect them to the Agent-net marketplace."""
    if dev:
        os.environ.setdefault("AGENTNET_ENV", "development")

    try:
        from .core.updater import maybe_auto_update  # noqa: PLC0415

        maybe_auto_update(quiet=True)
    except Exception:
        pass

    if os.environ.get("CLAUDECODE"):
        print(
            '<claude-code-hint v="1" type="plugin" value="agentnet@agentnet-cli" />',
            file=sys.stderr,
        )


@app.command()
def detect() -> None:
    """Scan your system for installed AI coding agents."""
    from .core.detect import detect_all
    from ..infra.paths import AgentName, agent_display_name, short_path

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
        None, "--url", help=f"Platform URL (default: {PRODUCTION_PLATFORM_URL})",
    ),
) -> None:
    """Sign in through the browser and register a CLI identity."""
    from .core.register import register_command

    register_command(platform_url=url)


@app.command()
def setup(
    url: Optional[str] = typer.Option(
        None, "--url", help=f"Platform URL (default: {PRODUCTION_PLATFORM_URL})",
    ),
    choose: bool = typer.Option(
        False,
        "--choose",
        help="Interactively choose which detected agents to configure",
    ),
) -> None:
    """Sign in and configure all detected agents (use --choose to pick individually)."""
    from .core.setup_wizard import setup_command

    setup_command(platform_url=url, choose=choose)


@app.command()
def connect(
    agent: Optional[str] = typer.Argument(
        None, help="Agent to connect (claude, cursor, copilot, vscode, codex, hermes, openclaw)",
    ),
    all_agents: bool = typer.Option(False, "--all", help="Connect all detected agents"),
) -> None:
    """Connect an agent to the Agent-net marketplace via MCP."""
    from .core.connect import connect_command

    connect_command(agent_name=agent, connect_all=all_agents)


@app.command()
def disconnect(
    agent: Optional[str] = typer.Argument(None, help="Agent to disconnect"),
    all_agents: bool = typer.Option(False, "--all", help="Disconnect all connected agents"),
) -> None:
    """Remove an agent's connection to Agent-net."""
    from .core.disconnect import disconnect_command

    disconnect_command(agent_name=agent, disconnect_all=all_agents)


@app.command()
def status() -> None:
    """Show registration and agent connection status."""
    from .core.status import status_command

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

    from ..infra.config import save_agent_path
    from ..infra.paths import AgentName, agent_display_name

    try:
        display = agent_display_name(AgentName(agent))
    except ValueError:
        console.print(f"[red]Error:[/red] Unknown agent [bold]{agent}[/bold]")
        console.print("  [dim]Available: claude, cursor, copilot, vscode, codex, hermes, openclaw[/dim]")
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
    from ..infra.config import remove_agent_path
    from ..infra.paths import AgentName, agent_display_name

    try:
        display = agent_display_name(AgentName(agent))
    except ValueError:
        console.print(f"[red]Error:[/red] Unknown agent [bold]{agent}[/bold]")
        console.print("  [dim]Available: claude, cursor, copilot, vscode, codex, hermes, openclaw[/dim]")
        raise SystemExit(1)

    if remove_agent_path(agent):
        console.print(f"[green]✓[/green] Cleared custom path for {display}")
    else:
        console.print(f"[dim]No custom path set for {display}[/dim]")


@app.command()
def update(
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
    background: bool = typer.Option(
        False,
        "--background",
        help="Start upgrade in background (integrations refresh on next run)",
    ),
    refresh_only: bool = typer.Option(
        False,
        "--refresh-only",
        hidden=True,
        help="Internal: refresh agent integrations at the current installed version",
    ),
) -> None:
    """Upgrade agentnet-cli and refresh connected agent integrations."""
    from .core.updater import clean_update, run_update  # noqa: PLC0415

    if refresh_only:
        result = clean_update(quiet=quiet, refresh_only=True)
        if not quiet and result.refreshed:
            console.print(f"  [green]✓[/green] Refreshed {result.refreshed} agent config(s)")
        elif not quiet:
            console.print("  [dim]All agent configs are up to date.[/dim]")
        return

    if not quiet:
        console.print()
        console.print("  [dim]Checking PyPI for updates...[/dim]")

    if background:
        result = run_update(quiet=quiet, background=True, force=True)
    else:
        result = clean_update(quiet=quiet)

    if quiet:
        if result.message and not result.upgraded and not result.upgrade_started:
            print(result.message, file=sys.stderr)
        return

    if result.upgrade_started:
        console.print(f"  [green]✓[/green] {result.message}")
        console.print("  [dim]Restart your agent to pick up the new version.[/dim]")
    elif result.upgraded:
        console.print(f"  [green]✓[/green] {result.message}")
        console.print("  [dim]Agent integrations refreshed.[/dim]")
    elif result.message and "failed" in result.message.lower():
        console.print(f"  [red]✗[/red] {result.message}")
        method = "pip install --upgrade agentnet-cli"
        console.print(f"  [dim]Try manually: {method}[/dim]")
    elif result.message == "Could not reach PyPI":
        console.print("  [yellow]![/yellow] Could not reach PyPI — refreshing local configs only")
    elif result.message:
        console.print(f"  {result.message}")

    if result.refreshed and not result.upgraded:
        console.print(f"  [dim]Refreshed {result.refreshed} agent config(s).[/dim]")
    elif result.checked and not result.upgraded and not result.upgrade_started and not result.refreshed:
        console.print("  [dim]All agent configs are up to date.[/dim]")

    console.print()


@app.command(name="mcp-serve", hidden=True)
def mcp_serve() -> None:
    """Start the AgentNet MCP server (internal)."""
    from ..tools.mcp_server import serve

    serve()


# -- Marketplace commands --
from .marketplace.agent import agent as _agent_fn  # noqa: E402
from .marketplace.discover import discover as _discover_fn  # noqa: E402

app.command(name="discover")(_discover_fn)
app.command(name="agent")(_agent_fn)
