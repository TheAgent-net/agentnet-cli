from __future__ import annotations

import re
import shutil
import subprocess
import sys

from rich.console import Console

from . import __version__
from .agents.registry import get_connector
from .config import load_config
from .manifest import load_manifest, record_connection
from .paths import AgentName

_err = Console(stderr=True)


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


def self_upgrade() -> tuple[bool, str]:
    """Upgrade agentnet-cli to latest. Returns (success, message)."""
    cmd = _upgrade_command()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            latest = check_pypi_latest()
            return True, latest or "latest"
        return False, result.stderr.strip()[:200]
    except Exception as e:
        return False, str(e)


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

    return [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]
