from __future__ import annotations

from rich.console import Console

from .agents.registry import get_connector
from .manifest import load_manifest, remove_connection
from .paths import AgentName, agent_display_name

console = Console()


def disconnect_command(agent_name: str | None = None, disconnect_all: bool = False) -> None:
    manifest = load_manifest()
    connections = manifest.get("connections", {})

    if disconnect_all:
        targets = list(connections.keys())
        if not targets:
            console.print("\n  [dim]No agents are currently connected.[/dim]\n")
            return
    elif agent_name:
        if agent_name not in connections:
            try:
                display = agent_display_name(AgentName(agent_name))
            except ValueError:
                display = agent_name
            console.print(f"\n  [yellow]![/yellow] {display} is not connected.\n")
            return
        targets = [agent_name]
    else:
        console.print("\n  [red]Error:[/red] Specify an agent name or use [bold]--all[/bold]")
        console.print("  [dim]Example: agentnet disconnect claude[/dim]\n")
        raise SystemExit(1)

    console.print()
    succeeded = 0
    for name in targets:
        try:
            agent = AgentName(name)
            display = agent_display_name(agent)
        except ValueError:
            console.print(f"  [yellow]![/yellow] Unknown agent {name}, skipping")
            continue

        connector = get_connector(agent)
        entry = connections[name]
        console.print(f"  Disconnecting {display}...")
        ok = connector.disconnect(entry)
        if ok:
            remove_connection(name)
            console.print(f"  [green]✓[/green] {display} disconnected")
            succeeded += 1
        else:
            console.print(f"  [red]✗[/red] {display} — failed to disconnect cleanly")

    if succeeded:
        console.print(
            f"\n  [green]{succeeded} agent{'s' if succeeded != 1 else ''} disconnected.[/green]"
        )
    console.print()
