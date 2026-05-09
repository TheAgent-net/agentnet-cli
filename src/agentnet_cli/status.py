from __future__ import annotations

from rich.console import Console
from rich.table import Table

from .config import load_config
from .detect import detect_all
from .paths import AgentName, agent_display_name, short_path

console = Console()


def status_command() -> None:
    config = load_config()
    if not config:
        console.print()
        console.print("  [yellow]Not registered.[/yellow] Run [bold]agentnet register[/bold] to get started.")
        console.print()
        return

    console.print()
    console.print("[bold]Platform[/bold]")
    console.print(f"  URL:    {config.get('platform_url')}")
    token = config.get("api_token", "")
    console.print(f"  Token:  [dim]...{token[-6:]}[/dim]" if len(token) > 6 else "  Token:  [dim]configured[/dim]")
    if config.get("wallet_id"):
        console.print(f"  Wallet: {config['wallet_id']}")

    results = detect_all()
    detected_count = sum(1 for r in results if r.detected)
    connected_count = sum(1 for r in results if r.already_connected)

    console.print()
    console.print("[bold]Agents[/bold]")

    table = Table(
        box=None, pad_edge=False, show_edge=False, padding=(0, 2),
        show_header=True, header_style="bold dim",
    )
    table.add_column("Agent", min_width=18)
    table.add_column("Detected", min_width=10, justify="center")
    table.add_column("Connected", min_width=11, justify="center")
    table.add_column("Binary")

    for r in results:
        display = agent_display_name(AgentName(r.agent_name))
        detected = "[green]✓[/green]" if r.detected else "[dim]—[/dim]"
        connected = "[green]✓[/green]" if r.already_connected else "[dim]—[/dim]"

        if r.binary_found:
            binary = f"[green]{short_path(r.binary_path)}[/green]"
        elif r.detected:
            binary = "[yellow]not in PATH[/yellow]"
        else:
            binary = "[dim]—[/dim]"

        table.add_row(display, detected, connected, binary)

    console.print(table)

    parts: list[str] = []
    parts.append(f"[bold]{detected_count}[/bold]/{len(results)} detected")
    parts.append(f"[green]{connected_count} connected[/green]" if connected_count else "0 connected")
    console.print(f"\n  {' · '.join(parts)}")
    console.print()
