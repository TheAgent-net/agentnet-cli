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
    help="Find AI coding agents on your system. Connect them to the Agent-net marketplace.",
    no_args_is_help=True,
)
console = Console()

# Internal hook commands that run on the agent's critical path — the callback skips auto-update for
# these so a tool call is never blocked; the detached worker handles it instead.
_HOOK_COMMANDS = {"skill-hook", "cursor-hook", "hermes-hook"}


def _configure_windows_stdio() -> None:
    """Prefer UTF-8 on Windows so Rich glyphs (●/○/✓) do not crash cp1252 consoles."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — best-effort console setup
                pass


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
    """Find AI coding agents on your system. Connect them to the Agent-net marketplace."""
    _configure_windows_stdio()
    if dev:
        os.environ.setdefault("AGENTNET_ENV", "development")

    # The hooks shell out to `agentnet` and fire on the agent's critical path (prompt submit, each
    # tool call, turn end), so the auto-update must NOT run here — a due PyPI check would block a
    # tool call. The detached `--fetch` worker runs it instead (see tools/hook.py::run_fetch), once
    # per turn, off the critical path. Every non-hook command still auto-updates as before.
    if not (len(sys.argv) > 1 and sys.argv[1] in _HOOK_COMMANDS):
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
def detect(
    env: Optional[str] = typer.Option(
        None, "--env", help="Scope to environment: local|windows|wsl[:distro]",
    ),
    no_mirror: bool = typer.Option(
        False, "--no-mirror", help="Skip WSL/Windows auto-mirroring",
    ),
) -> None:
    """Scan your system for installed AI coding agents."""
    from .core.detect import detect_all
    from ..infra.paths import AgentName, agent_display_name, short_path

    results = detect_all(env_filter=env, no_mirror=no_mirror)
    detected_count = sum(1 for r in results if r.detected)
    connected_count = sum(1 for r in results if r.already_connected)
    ready_count = sum(1 for r in results if r.detected and not r.already_connected)

    table = Table(
        box=None, pad_edge=False, show_edge=False, padding=(0, 2),
        show_header=True, header_style="bold dim",
    )
    table.add_column("Agent", min_width=18)
    table.add_column("Environment", min_width=16)
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
        elif r.detected and r.env_key == "local":
            binary = "[yellow]not in PATH[/yellow]"
        else:
            binary = "[dim]—[/dim]"

        table.add_row(display, r.env_label, status, binary)

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
        help="Choose which detected agents to configure",
    ),
    env: Optional[str] = typer.Option(
        None, "--env", help="Scope to environment: local|windows|wsl[:distro]",
    ),
    no_mirror: bool = typer.Option(
        False, "--no-mirror", help="Skip WSL/Windows auto-mirroring",
    ),
) -> None:
    """Configure detected agents, then optionally sign in. Use --choose to pick agents one by one."""
    from .core.setup_wizard import setup_command

    setup_command(platform_url=url, choose=choose, env_filter=env, no_mirror=no_mirror)


@app.command()
def connect(
    agent: Optional[str] = typer.Argument(
        None, help="Agent to connect (claude, cursor, copilot, vscode, codex, hermes, openclaw)",
    ),
    all_agents: bool = typer.Option(False, "--all", help="Connect all detected agents"),
    env: Optional[str] = typer.Option(
        None, "--env", help="Scope to environment: local|windows|wsl[:distro]",
    ),
    no_mirror: bool = typer.Option(
        False, "--no-mirror", help="Skip WSL/Windows auto-mirroring",
    ),
) -> None:
    """Connect an agent to the Agent-net marketplace via MCP."""
    from .core.connect import connect_command

    connect_command(
        agent_name=agent, connect_all=all_agents, env_filter=env, no_mirror=no_mirror,
    )


@app.command()
def disconnect(
    agent: Optional[str] = typer.Argument(None, help="Agent to disconnect"),
    all_agents: bool = typer.Option(False, "--all", help="Disconnect all connected agents"),
    env: Optional[str] = typer.Option(
        None, "--env", help="Scope to environment: local|windows|wsl[:distro]",
    ),
    no_mirror: bool = typer.Option(
        False, "--no-mirror", help="Skip WSL/Windows auto-mirroring",
    ),
) -> None:
    """Remove an agent's connection to Agent-net."""
    from .core.disconnect import disconnect_command

    disconnect_command(
        agent_name=agent, disconnect_all=all_agents, env_filter=env, no_mirror=no_mirror,
    )


@app.command()
def status(
    env: Optional[str] = typer.Option(
        None, "--env", help="Scope to environment: local|windows|wsl[:distro]",
    ),
    no_mirror: bool = typer.Option(
        False, "--no-mirror", help="Skip WSL/Windows auto-mirroring",
    ),
) -> None:
    """Show registration and agent connection status."""
    from .core.status import status_command

    status_command(env_filter=env, no_mirror=no_mirror)


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
    """Remove a custom binary path. Use auto-detection again."""
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
        help="Start upgrade in the background. Integrations refresh on the next run.",
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


@app.command(name="skill-hook", hidden=True)
def skill_hook(
    pre: bool = typer.Option(False, "--pre", help="UserPromptSubmit: start the discovery worker"),
    peek: bool = typer.Option(False, "--peek", help="PostToolUse: guide the agent during the turn"),
    post: bool = typer.Option(False, "--post", help="Stop: add relevant AgentNet skills"),
    fetch: bool = typer.Option(False, "--fetch", help="Detached worker: discover + cache (internal)"),
    session: str = typer.Option("", "--session", help="Session id (worker)"),
    query: str = typer.Option("", "--query", help="Prompt text (worker)"),
    limit: int = typer.Option(6, "--limit", help="Max skills to suggest"),
    classifier: str = typer.Option(
        "claude", "--classifier", help="Gate CLI backend: claude | cursor (worker)",
    ),
    hook_timeout: float = typer.Option(
        3.0, "--timeout", help="Max seconds a hook waits for the subagent result",
    ),
) -> None:
    """Claude Code hooks that show AgentNet skills (internal).

    ``--pre`` (UserPromptSubmit) starts a discovery worker. ``--peek`` (PostToolUse) guides
    the agent when results are ready. ``--post`` (Stop) is the fallback. On error, exit 0
    and do nothing.
    """
    from ..tools.claude_hook import run_claude_peek, run_claude_post, run_claude_pre
    from ..tools.skillfire import run_fetch

    if fetch:
        run_fetch(
            session=session, query=query, limit=limit, timeout=hook_timeout, classifier=classifier
        )
    elif pre:
        run_claude_pre(limit=limit, timeout=hook_timeout)
    elif peek:
        run_claude_peek(limit=limit, timeout=hook_timeout)
    else:  # default and --post
        run_claude_post(limit=limit, timeout=hook_timeout)


@app.command(name="cursor-hook", hidden=True)
def cursor_hook(
    pre: bool = typer.Option(False, "--pre", help="beforeSubmitPrompt: start the discovery worker"),
    peek: bool = typer.Option(False, "--peek", help="preToolUse: guide the agent (deny once)"),
    post: bool = typer.Option(False, "--post", help="stop: add relevant AgentNet skills"),
    limit: int = typer.Option(6, "--limit", help="Max skills to suggest"),
    hook_timeout: float = typer.Option(
        3.0, "--timeout", help="Max seconds a hook waits for the worker's result",
    ),
) -> None:
    """Cursor hooks that show AgentNet skills (internal).

    ``--pre`` (beforeSubmitPrompt) starts the discovery worker. ``--peek`` (preToolUse) blocks
    the first tool call once and sends the skill to the agent. ``--post`` (stop) is the
    fallback. On error, exit 0 and do nothing.
    """
    from ..tools.cursor_hook import run_cursor_peek, run_cursor_post, run_cursor_pre

    if pre:
        run_cursor_pre(limit=limit, timeout=hook_timeout)
    elif peek:
        run_cursor_peek(limit=limit, timeout=hook_timeout)
    else:  # default and --post
        run_cursor_post(limit=limit, timeout=hook_timeout)


@app.command(name="hermes-hook", hidden=True)
def hermes_hook(
    pre: bool = typer.Option(False, "--pre", help="pre_llm_call: start the discovery worker"),
    peek: bool = typer.Option(False, "--peek", help="pre_tool_call: guide the agent"),
    post: bool = typer.Option(False, "--post", help="pre_verify: continue the turn (fallback)"),
    limit: int = typer.Option(6, "--limit", help="Max skills to suggest"),
    hook_timeout: float = typer.Option(
        3.0, "--timeout", help="Max seconds a hook waits for the worker's result",
    ),
) -> None:
    """Hermes shell hooks that show AgentNet skills (internal).

    ``--pre`` (pre_llm_call) starts the discovery worker. ``--peek`` (pre_tool_call) blocks one
    tool call and returns the skill to the model. ``--post`` (pre_verify) continues the turn as
    a fallback. On error, return ``{}`` and exit 0.
    """
    from ..tools.hermes_hook import run_hermes_peek, run_hermes_post, run_hermes_pre

    if pre:
        run_hermes_pre(limit=limit, timeout=hook_timeout)
    elif peek:
        run_hermes_peek(limit=limit, timeout=hook_timeout)
    else:  # default and --post
        run_hermes_post(limit=limit, timeout=hook_timeout)


@app.command(name="enable-skill-fire")
def enable_skill_fire(
    remove: bool = typer.Option(False, "--remove", help="Remove the hook instead of installing"),
) -> None:
    """Run AgentNet on every Claude Code prompt. Writes ~/.claude/settings.json."""
    from ..connectors.claude_search_hook import SettingsHookError, install, uninstall

    try:
        changed, path = uninstall() if remove else install()
    except SettingsHookError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc
    action = "removed" if remove else "installed"
    if changed:
        console.print(f"[green]✓[/green] AgentNet skill hook {action} in [bold]{path}[/bold]")
        if not remove:
            console.print("  [dim]Restart Claude Code — every prompt now fires AgentNet.[/dim]")
    else:
        state = "not present" if remove else "already installed"
        console.print(f"[dim]No change ({state}): {path}[/dim]")


# -- Marketplace commands --
from .marketplace.agent import agent as _agent_fn  # noqa: E402
from .marketplace.discover import discover as _discover_fn  # noqa: E402

app.command(name="discover")(_discover_fn)
app.command(name="agent")(_agent_fn)
