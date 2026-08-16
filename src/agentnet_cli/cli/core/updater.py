from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass

from rich.console import Console

from agentnet_cli import __version__
from ...connectors.registry import get_connector
from ...infra.config import load_config
from ...infra.environments import (
    detect_environments,
    parse_connection_key,
)
from ...infra.manifest import load_manifest, record_connection, record_update_check, should_check_for_update
from ...infra.paths import AgentName
from ...infra.proc import agentnet_invocation, find_executable, run_tool, start_detached_process

_err = Console(stderr=True)

_DEFAULT_CHECK_INTERVAL_HOURS = 24.0


@dataclass
class AutoUpdateResult:
    checked: bool = False
    upgrade_started: bool = False
    upgraded: bool = False
    refreshed: int = 0
    message: str | None = None


def _auto_update_enabled() -> bool:
    return os.environ.get("AGENTNET_AUTO_UPDATE", "1").strip().lower() not in {"0", "false", "no"}


def _check_interval_hours() -> float:
    raw = os.environ.get("AGENTNET_UPDATE_CHECK_INTERVAL_HOURS", "").strip()
    if not raw:
        return _DEFAULT_CHECK_INTERVAL_HOURS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_CHECK_INTERVAL_HOURS


def refresh_stale_connections(*, quiet: bool = False) -> int:
    """Call connect() again for agents whose manifest cli_version differs from the current version."""
    config = load_config()
    if not config or not config.get("api_token"):
        return 0

    manifest = load_manifest()
    connections = manifest.get("connections", {})
    if not connections:
        return 0

    envs_by_key = {e.key: e for e in detect_environments()}
    refreshed = 0
    for conn_key, conn_info in list(connections.items()):
        if conn_info.get("cli_version") == __version__:
            continue

        try:
            agent_name, env_key = parse_connection_key(conn_key)
            # Prefer env metadata stored on the record when present.
            env_key = conn_info.get("env") or env_key
            agent_enum = AgentName(agent_name)
            env = envs_by_key.get(env_key)
            if env is None and env_key == "local":
                from ...infra.environments import local_environment  # noqa: PLC0415

                env = local_environment()
            if env is None:
                continue
            connector = get_connector(agent_enum, env)
            detection = connector.detect()
            if not detection.detected:
                continue

            result = connector.connect(config)
            if result.success:
                record_connection(
                    conn_key,
                    files_created=result.files_created,
                    files_modified=result.files_modified,
                    mcp_entry=result.mcp_entry,
                    env_key=env.key,
                    env_label=env.label,
                )
                refreshed += 1
            else:
                print(f"Warning: refresh for {conn_key} returned success=False", file=sys.stderr)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Warning: failed to refresh {conn_key}: {exc}", file=sys.stderr)
            continue

    if refreshed and not quiet:
        _err.print(
            f"  [dim]Refreshed {refreshed} agent config(s) for v{__version__}[/dim]"
        )

    return refreshed


def check_pypi_latest() -> str | None:
    """Check PyPI for the latest published version."""
    try:
        import httpx  # noqa: PLC0415

        resp = httpx.get(
            "https://pypi.org/pypi/agentnet-cli/json",
            timeout=5.0,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.json()["info"]["version"]
    except Exception:
        pass
    return None


def detect_install_method() -> str:
    """Return a readable label for the upgrade method."""
    cmd = _upgrade_command()
    if len(cmd) >= 2 and cmd[1] == "tool":
        return "uv tool"
    if "pipx" in cmd[0]:
        return "pipx"
    if "npm" in cmd[0]:
        return "npm"
    return "pip"


def self_upgrade(*, background: bool = False, verbose: bool = False) -> tuple[bool, str]:
    """Upgrade agentnet-cli to latest. Returns (success, message)."""
    cmd = _upgrade_command()
    try:
        if background:
            start_detached_process(cmd)
            latest = check_pypi_latest()
            return True, latest or "latest"

        if verbose:
            result = subprocess.run(cmd, timeout=300)  # noqa: S603
            detail = ""
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # noqa: S603
            detail = result.stderr.strip()[:200]

        if result.returncode == 0:
            latest = check_pypi_latest()
            return True, latest or "latest"
        return False, detail or f"exit code {result.returncode}"
    except Exception as e:
        return False, str(e)


def _spawn_refresh_with_upgraded_binary(*, quiet: bool = False) -> int:
    """Call the upgraded agentnet binary again. This refreshes integrations at the new version."""
    args = ["update", "--refresh-only"]
    if quiet:
        args.append("--quiet")
    inv = agentnet_invocation()
    try:
        proc = subprocess.run([*inv, *args], timeout=120)  # noqa: S603
        return proc.returncode
    except Exception:
        return 0


def clean_update(*, quiet: bool = False, refresh_only: bool = False) -> AutoUpdateResult:
    """Upgrade the package, then refresh integrations from the new install."""
    if refresh_only:
        refreshed = refresh_stale_connections(quiet=quiet)
        return AutoUpdateResult(checked=True, refreshed=refreshed)

    result = AutoUpdateResult(checked=True)
    latest = check_pypi_latest()
    record_update_check()

    if latest is None:
        result.message = "Could not reach PyPI"
        result.refreshed = refresh_stale_connections(quiet=quiet)
        return result

    if latest == __version__:
        result.message = f"Already on latest version ({__version__})"
        result.refreshed = refresh_stale_connections(quiet=quiet)
        return result

    method = detect_install_method()
    if not quiet:
        _err.print(
            f"  Upgrading [bold]{__version__}[/bold] → [bold]{latest}[/bold] via {method}..."
        )

    ok, msg = self_upgrade(background=False, verbose=not quiet)
    if not ok:
        result.message = f"Upgrade failed: {msg}"
        return result

    result.upgraded = True
    result.message = f"Upgraded to {msg}"
    record_update_check(upgraded_to=msg)

    if not quiet:
        _err.print("  [dim]Refreshing agent integrations...[/dim]")

    _spawn_refresh_with_upgraded_binary(quiet=quiet)
    return result


def run_update(*, quiet: bool = False, background: bool = False, force: bool = False) -> AutoUpdateResult:
    """Check PyPI, upgrade if needed, then refresh stale agent integrations."""
    result = AutoUpdateResult()
    interval = _check_interval_hours()

    if not force and not should_check_for_update(interval):
        result.refreshed = refresh_stale_connections(quiet=quiet)
        return result

    result.checked = True
    latest = check_pypi_latest()
    record_update_check()

    if latest is None:
        result.message = "Could not reach PyPI"
        result.refreshed = refresh_stale_connections(quiet=quiet)
        if not quiet:
            _err.print("  [yellow]![/yellow] Could not reach PyPI — skipping version check")
        return result

    if _auto_update_enabled() and latest != __version__:
        ok, msg = self_upgrade(background=background)
        if ok:
            if background:
                result.upgrade_started = True
                result.message = f"Upgrade to {msg} started in background"
            else:
                result.upgraded = True
                result.message = f"Upgraded to {msg}"
                record_update_check(upgraded_to=msg)
        else:
            result.message = f"Upgrade failed: {msg}"
            if not quiet:
                _err.print(f"  [red]✗[/red] Upgrade failed: {msg}")
    elif not quiet and latest == __version__:
        result.message = f"Already on latest version ({__version__})"

    result.refreshed = refresh_stale_connections(quiet=quiet)
    return result


def maybe_auto_update(*, quiet: bool = True) -> AutoUpdateResult:
    """Run a rate-limited silent auto-update for the CLI callback and MCP startup."""
    if not _auto_update_enabled():
        refreshed = refresh_stale_connections(quiet=quiet)
        return AutoUpdateResult(refreshed=refreshed)
    return run_update(quiet=quiet, background=True)


def _upgrade_command() -> list[str]:
    """Find the install method and return the upgrade command with absolute paths."""
    uv = find_executable("uv")
    if uv:
        try:
            r = run_tool("uv", ["tool", "list"], timeout=10, text=True)
            if r is not None and re.search(r"^agentnet-cli\b", r.stdout or "", re.MULTILINE):
                return [uv, "tool", "upgrade", "agentnet-cli"]
        except Exception:
            pass

    pipx = find_executable("pipx")
    if pipx:
        try:
            r = run_tool("pipx", ["list", "--short"], timeout=10, text=True)
            if r is not None and re.search(r"^agentnet-cli\b", r.stdout or "", re.MULTILINE):
                return [pipx, "upgrade", "agentnet-cli"]
        except Exception:
            pass

    npm = find_executable("npm")
    if npm:
        try:
            r = run_tool(
                "npm",
                ["list", "-g", "--depth=0", "agentnet-cli"],
                timeout=10,
                text=True,
            )
            if r is not None and re.search(r"^agentnet-cli@", r.stdout or "", re.MULTILINE):
                return [npm, "install", "-g", "agentnet-cli@latest"]
        except Exception:
            pass

    return [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]
