"""Connect CLI command for Agent-net agents."""

from __future__ import annotations

from rich.console import Console

from ...connectors.registry import get_connector
from ...infra.config import load_config
from ...infra.credentials import ensure_guest_credentials
from ...infra.environments import (
    connection_key,
    detect_environments,
    resolve_env_filter,
)
from .detect import detect_all
from ...infra.manifest import record_connection
from ...infra.paths import AgentName, agent_display_name

console = Console()


def connect_command(
    agent_name: str | None = None,
    connect_all: bool = False,
    *,
    env_filter: str | None = None,
    no_mirror: bool = False,
) -> None:
    """Connect agents to the Agent-net platform.

    Ensures a guest API token exists when none is saved, then wires harnesses.
    Browser login later elevates the guest identity.
    """
    try:
        config = ensure_guest_credentials()
    except Exception as exc:
        console.print(f"\n  [yellow]![/yellow] Guest bootstrap skipped: {exc}")
        config = load_config() or {}

    envs = resolve_env_filter(env_filter, detect_environments(no_mirror=no_mirror))
    results = detect_all(env_filter=env_filter, no_mirror=no_mirror)

    if connect_all:
        targets = [
            (r.agent_name, r.env_key)
            for r in results
            if r.detected and not r.already_connected
        ]
        if not targets:
            console.print("\n  [dim]All detected agents are already connected.[/dim]\n")
            return
    elif agent_name:
        try:
            AgentName(agent_name)
        except ValueError:
            console.print(f"\n  [red]Error:[/red] Unknown agent [bold]{agent_name}[/bold]")
            console.print(
                "  [dim]Available: claude, cursor, copilot, vscode, codex, hermes, openclaw[/dim]\n"
            )
            raise SystemExit(1)
        targets = [
            (agent_name, r.env_key)
            for r in results
            if r.agent_name == agent_name and r.detected
        ]
        if not targets:
            # Still try local even if undetected — keeps prior single-env behavior.
            targets = [(agent_name, e.key) for e in envs]
    else:
        console.print("\n  [red]Error:[/red] Specify an agent name or use [bold]--all[/bold]")
        console.print("  [dim]Example: agentnet connect claude[/dim]\n")
        raise SystemExit(1)

    envs_by_key = {e.key: e for e in envs}
    console.print()
    succeeded = 0
    for name, env_key in targets:
        env = envs_by_key.get(env_key)
        if env is None:
            continue
        display = agent_display_name(AgentName(name))
        label = display if env.kind == "local" else f"{display} — {env.label}"
        connector = get_connector(AgentName(name), env)
        detection = connector.detect()
        if not detection.detected:
            console.print(f"  [yellow]![/yellow] {label} not detected, skipping")
            continue

        console.print(f"  Connecting {label}...")
        result = connector.connect(config)
        if result.success:
            key = connection_key(name, env)
            record_connection(
                key,
                files_created=result.files_created,
                files_modified=result.files_modified,
                mcp_entry=result.mcp_entry,
                env_key=env.key,
                env_label=env.label,
            )
            file_count = len(result.files_created)
            mcp_info = " + MCP server registered" if result.mcp_entry else ""
            console.print(
                f"  [green]✓[/green] {label} connected "
                f"({file_count} file{'s' if file_count != 1 else ''} created{mcp_info})"
            )
            for err in result.errors:
                console.print(f"    [dim]note: {err}[/dim]")
            succeeded += 1
        else:
            console.print(f"  [red]✗[/red] {label} failed: {', '.join(result.errors)}")

    if succeeded:
        console.print(f"\n  [green]{succeeded} agent{'s' if succeeded != 1 else ''} connected.[/green]")
        from ...infra.credentials import is_authenticated  # noqa: PLC0415

        if is_authenticated(config=config):
            console.print("  [dim]Your agents can now discover and transact on Agent-net.[/dim]")
        else:
            console.print(
                "  [dim]Hooks are live with a guest token. "
                "Run [bold]agentnet register[/bold] to elevate and raise limits.[/dim]"
            )
    console.print()
