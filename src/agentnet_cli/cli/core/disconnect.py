"""Disconnect CLI command for Agent-net agents."""

from __future__ import annotations

from rich.console import Console

from ...connectors.registry import get_connector
from ...infra.environments import (
    detect_environments,
    parse_connection_key,
    resolve_env_filter,
)
from ...infra.manifest import load_manifest, remove_connection
from ...infra.paths import AgentName, agent_display_name

console = Console()


def disconnect_command(
    agent_name: str | None = None,
    disconnect_all: bool = False,
    *,
    env_filter: str | None = None,
    no_mirror: bool = False,
) -> None:
    """Disconnect agents from Agent-net.

    Disconnect one agent, all connected agents, or agents in filtered environments.
    """
    manifest = load_manifest()
    connections = manifest.get("connections", {})
    envs = resolve_env_filter(env_filter, detect_environments(no_mirror=no_mirror))
    envs_by_key = {e.key: e for e in envs}
    # Always allow local even if filter somehow empty
    from ...infra.environments import local_environment  # noqa: PLC0415

    envs_by_key.setdefault("local", local_environment())

    if disconnect_all:
        targets = list(connections.keys())
        if env_filter:
            allowed = {e.key for e in envs}
            targets = [
                k for k in targets
                if parse_connection_key(k)[1] in allowed
                or connections.get(k, {}).get("env", "local") in allowed
            ]
        if not targets:
            console.print("\n  [dim]No agents are currently connected.[/dim]\n")
            return
    elif agent_name:
        # Match bare agent and agent@env keys
        matches = [
            k for k in connections
            if k == agent_name or k.startswith(f"{agent_name}@")
        ]
        if env_filter:
            allowed = {e.key for e in envs}
            matches = [
                k for k in matches
                if parse_connection_key(k)[1] in allowed
                or connections.get(k, {}).get("env", "local") in allowed
            ]
        if not matches:
            try:
                display = agent_display_name(AgentName(agent_name))
            except ValueError:
                display = agent_name
            console.print(f"\n  [yellow]![/yellow] {display} is not connected.\n")
            return
        targets = matches
    else:
        console.print("\n  [red]Error:[/red] Specify an agent name or use [bold]--all[/bold]")
        console.print("  [dim]Example: agentnet disconnect claude[/dim]\n")
        raise SystemExit(1)

    console.print()
    succeeded = 0
    for key in targets:
        agent_str, env_key = parse_connection_key(key)
        env_key = connections.get(key, {}).get("env") or env_key
        try:
            agent = AgentName(agent_str)
            display = agent_display_name(agent)
        except ValueError:
            console.print(f"  [yellow]![/yellow] Unknown agent {key}, skipping")
            continue

        env = envs_by_key.get(env_key)
        if env is None:
            from ...infra.environments import Environment  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            env = Environment(
                kind=env_key.split(":")[0] if env_key != "local" else "local",
                label=connections.get(key, {}).get("env_label") or env_key,
                home=Path.home(),
                distro=env_key.split(":", 1)[1] if env_key.startswith("wsl:") else None,
            )

        label = display if env.kind == "local" else f"{display} — {env.label}"
        connector = get_connector(agent, env)
        entry = connections[key]
        console.print(f"  Disconnecting {label}...")
        ok = connector.disconnect(entry)
        if ok:
            remove_connection(key)
            console.print(f"  [green]✓[/green] {label} disconnected")
            succeeded += 1
        else:
            console.print(f"  [red]✗[/red] {label} — failed to disconnect cleanly")

    if succeeded:
        console.print(
            f"\n  [green]{succeeded} agent{'s' if succeeded != 1 else ''} disconnected.[/green]"
        )
    console.print()
