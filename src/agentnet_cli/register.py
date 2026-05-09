from __future__ import annotations

import os

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config, save_config
from .platform.client import PlatformClient

console = Console()

DEFAULT_PLATFORM_URL = "https://app.agentnet.market"


def register_command(platform_url: str | None = None) -> None:
    existing = load_config()
    if existing and existing.get("api_token"):
        console.print(f"\n  [green]Already registered[/green] on {existing.get('platform_url')}")
        if not typer.confirm("  Re-register?"):
            return

    url = platform_url or os.environ.get("AGENTNET_URL") or DEFAULT_PLATFORM_URL

    console.print()
    api_token = typer.prompt("  API token", hide_input=True)

    client = PlatformClient(base_url=url, api_token=api_token)

    console.print("  [dim]Verifying token...[/dim]")
    try:
        info = client.token_info()
    except Exception as exc:
        console.print(f"  [red]✗[/red] Failed to verify token: {exc}\n")
        raise typer.Exit(1) from exc

    org_id = info["org_id"]
    org_name = info.get("org_name") or org_id
    console.print(f"  [green]✓[/green] Authenticated — org: [bold]{org_name}[/bold] ({org_id})")

    agents = info.get("agents") or []
    agent_id: str | None = None
    agent_api_key: str | None = None

    if info.get("agent_id"):
        agent_id = info["agent_id"]
        console.print(
            f"  [green]✓[/green] Token bound to agent: [bold]{info.get('agent_name')}[/bold] ({agent_id})"
        )
    elif agents:
        console.print(f"\n  Found {len(agents)} agent(s) in this org:\n")
        table = Table(show_header=True, box=None, pad_edge=False, show_edge=False, header_style="bold dim")
        table.add_column("#", style="dim", width=4)
        table.add_column("Name")
        table.add_column("Agent ID", style="dim")
        table.add_column("Type")
        table.add_column("Status")
        for i, a in enumerate(agents, 1):
            table.add_row(
                f"  {i}", a["name"], a["agent_id"], a.get("agent_type", ""), a["status"]
            )
        console.print(table)

        choice = typer.prompt(
            "\n  Use an existing agent or create a new one? (number or 'new')",
            default="new",
        )
        if choice.lower() == "new":
            agent_id, agent_api_key = _create_agent(client)
        else:
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(agents):
                    console.print("[red]Invalid selection[/red]")
                    raise SystemExit(1)
                agent_id = agents[idx]["agent_id"]
                console.print(f"  [green]✓[/green] Using agent: {agents[idx]['name']} ({agent_id})")
            except (ValueError, IndexError):
                console.print("  [red]✗[/red] Invalid choice\n")
                raise typer.Exit(1)
    else:
        console.print("\n  No agents in this org yet. Let's create one.\n")
        agent_id, agent_api_key = _create_agent(client)

    config = {
        "platform_url": url,
        "api_token": agent_api_key or api_token,
        "org_id": org_id,
        "agent_id": agent_id,
    }
    save_config(config)

    console.print()
    console.print("  [green]✓ Registered successfully.[/green]")
    console.print("  [dim]Config saved to ~/.agentnet/config.json[/dim]")
    console.print()
    console.print("  [bold]Next steps:[/bold]")
    console.print("    1. agentnet detect        [dim]— find agents on your system[/dim]")
    console.print("    2. agentnet connect <agent>[dim] — connect an agent to Agent-net[/dim]")
    console.print()


def _create_agent(client: PlatformClient) -> tuple[str, str | None]:
    name = typer.prompt("  Agent name")

    console.print()
    console.print("  [bold]Visibility:[/bold]")
    console.print("    [cyan]public[/cyan]  — listed on marketplace, A2A endpoint exposed")
    console.print("    [cyan]private[/cyan] — not listed, can only consume services")
    console.print()
    visibility = typer.prompt("  Public or private?", default="private", type=str).lower()
    if visibility not in ("public", "private"):
        visibility = "private"

    description = ""
    url = ""
    if visibility == "public":
        description = typer.prompt("  Description (what does your agent do?)", default="")
        url = typer.prompt("  A2A endpoint URL (where agents reach yours)", default="")

    console.print("  [dim]Creating agent...[/dim]")
    try:
        result = client.cli_register_agent(
            name=name,
            visibility=visibility,
            description=description,
            url=url,
        )
    except Exception as exc:
        console.print(f"  [red]✗[/red] Failed to create agent: {exc}\n")
        raise typer.Exit(1) from exc

    agent_id = result["agent_id"]
    agent_name = result["agent_name"]
    new_key = result.get("api_key")
    seed = result.get("seed_balance_usd", 0)

    console.print(f"  [green]✓[/green] Created [bold]{agent_name}[/bold] ({agent_id})")
    console.print(f"    Type: {result.get('visibility', visibility)}")
    if seed:
        console.print(f"    Seed balance: ${seed:.2f}")
    if new_key:
        console.print(f"    API key: [dim]{new_key[:12]}...[/dim] (saved to config)")

    return agent_id, new_key
