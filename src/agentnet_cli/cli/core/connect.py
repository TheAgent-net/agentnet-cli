from __future__ import annotations

from rich.console import Console

from ...connectors.registry import get_connector
from ...infra.config import load_config
from ...infra.credentials import ensure_guest_credentials
from .detect import detect_all
from ...infra.manifest import record_connection
from ...infra.paths import AgentName, agent_display_name

console = Console()


def connect_command(agent_name: str | None = None, connect_all: bool = False) -> None:
    """Connect agents to the Agent-net platform.

    Ensures a guest API token exists when none is saved, then wires harnesses.
    Browser login later elevates the guest identity.
    """
    try:
        config = ensure_guest_credentials()
    except Exception as exc:
        console.print(f"\n  [yellow]![/yellow] Guest bootstrap skipped: {exc}")
        config = load_config() or {}

    if not config.get("api_token"):
        console.print()
        console.print(
            "  [red]No AgentNet credentials.[/red] "
            "Run [bold]agentnet setup[/bold] or [bold]agentnet register[/bold] first."
        )
        console.print()
        raise SystemExit(1)

    if connect_all:
        targets = [r.agent_name for r in detect_all() if r.detected and not r.already_connected]
        if not targets:
            console.print("\n  [dim]All detected agents are already connected.[/dim]\n")
            return
    elif agent_name:
        try:
            AgentName(agent_name)
            targets = [agent_name]
        except ValueError:
            console.print(f"\n  [red]Error:[/red] Unknown agent [bold]{agent_name}[/bold]")
            console.print(
                "  [dim]Available: claude, cursor, copilot, vscode, codex, hermes, openclaw[/dim]\n"
            )
            raise SystemExit(1)
    else:
        console.print("\n  [red]Error:[/red] Specify an agent name or use [bold]--all[/bold]")
        console.print("  [dim]Example: agentnet connect claude[/dim]\n")
        raise SystemExit(1)

    console.print()
    succeeded = 0
    for name in targets:
        display = agent_display_name(AgentName(name))
        connector = get_connector(AgentName(name))
        detection = connector.detect()
        if not detection.detected:
            console.print(f"  [yellow]![/yellow] {display} not detected on this system, skipping")
            continue

        console.print(f"  Connecting {display}...")
        result = connector.connect(config)
        if result.success:
            record_connection(
                name,
                files_created=result.files_created,
                files_modified=result.files_modified,
                mcp_entry=result.mcp_entry,
            )
            file_count = len(result.files_created)
            mcp_info = " + MCP server registered" if result.mcp_entry else ""
            console.print(
                f"  [green]✓[/green] {display} connected "
                f"({file_count} file{'s' if file_count != 1 else ''} created{mcp_info})"
            )
            succeeded += 1
        else:
            console.print(f"  [red]✗[/red] {display} failed: {', '.join(result.errors)}")

    if succeeded:
        console.print(f"\n  [green]{succeeded} agent{'s' if succeeded != 1 else ''} connected.[/green]")
        console.print("  [dim]Your agents can now discover and transact on Agent-net.[/dim]")
    console.print()
