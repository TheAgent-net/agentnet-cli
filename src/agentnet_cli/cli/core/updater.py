from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from rich.console import Console

from agentnet_cli import __version__
from ...connectors.registry import get_connector
from ...infra.config import load_config
from ...infra.manifest import load_manifest, record_connection, record_update_check, should_check_for_update
from ...infra.paths import AgentName

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
    """Re-run connect() for agents whose manifest cli_version != current version."""
    config = load_config()
    if not config or not config.get("api_token"):
        return 0

    manifest = load_manifest()
    connections = manifest.get("connections", {})
    if not connections:
        return 0

    refreshed = 0
    for agent_name, conn_info in list(connections.items()):
        if conn_info.get("cli_version") == __version__:
            continue

        try:
            agent_enum = AgentName(agent_name)
            connector = get_connector(agent_enum)
            detection = connector.detect()
            if not detection.detected:
                continue

            result = connector.connect(config)
            if result.success:
                record_connection(
                    agent_name,
                    files_created=result.files_created,
                    files_modified=result.files_modified,
                    mcp_entry=result.mcp_entry,
                )
                refreshed += 1
            else:
                print(f"Warning: refresh for {agent_name} returned success=False", file=sys.stderr)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Warning: failed to refresh {agent_name}: {exc}", file=sys.stderr)
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
    """Human-readable label for how this install will be upgraded."""
    cmd = _upgrade_command()
    if cmd[:2] == ["uv", "tool"]:
        return "uv tool"
    if cmd[0] == "pipx":
        return "pipx"
    if cmd[0] == "npm":
        return "npm"
    return "pip"


def self_upgrade(*, background: bool = False, verbose: bool = False) -> tuple[bool, str]:
    """Upgrade agentnet-cli to latest. Returns (success, message)."""
    cmd = _upgrade_command()
    try:
        if background:
            subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
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
    """Re-invoke the upgraded agentnet binary so integrations refresh at the new version."""
    agentnet_bin = shutil.which("agentnet")
    args = ["update", "--refresh-only"]
    if quiet:
        args.append("--quiet")
    if agentnet_bin:
        proc = subprocess.run([agentnet_bin, *args], timeout=120)  # noqa: S603
        return proc.returncode
    return 0


def clean_update(*, quiet: bool = False, refresh_only: bool = False) -> AutoUpdateResult:
    """User-facing update: upgrade the package, then refresh integrations from the new install."""
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
    """Rate-limited silent auto-update used by CLI callback and MCP startup."""
    if not _auto_update_enabled():
        refreshed = refresh_stale_connections(quiet=quiet)
        return AutoUpdateResult(refreshed=refreshed)
    return run_update(quiet=quiet, background=True)


def _upgrade_command() -> list[str]:
    """Detect install method and return the right upgrade command."""
    if shutil.which("uv"):
        try:
            r = subprocess.run(
                ["uv", "tool", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if re.search(r"^agentnet-cli\b", r.stdout, re.MULTILINE):
                return ["uv", "tool", "upgrade", "agentnet-cli"]
        except Exception:
            pass

    if shutil.which("pipx"):
        try:
            r = subprocess.run(
                ["pipx", "list", "--short"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if re.search(r"^agentnet-cli\b", r.stdout, re.MULTILINE):
                return ["pipx", "upgrade", "agentnet-cli"]
        except Exception:
            pass

    if shutil.which("npm"):
        try:
            r = subprocess.run(
                ["npm", "list", "-g", "--depth=0", "agentnet-cli"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if re.search(r"^agentnet-cli@", r.stdout, re.MULTILINE):
                return ["npm", "install", "-g", "agentnet-cli@latest"]
        except Exception:
            pass

    return [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]
