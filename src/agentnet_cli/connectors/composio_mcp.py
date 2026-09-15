"""Register Composio Connect as a sibling HTTP MCP server.

AgentNet is the discovery layer (stdio `agentnet` MCP). Composio is the action
layer for GitHub, Slack, Linear, and 1000+ other apps. Connectors merge a
`composio` entry pointing at https://connect.composio.dev/mcp — they never wrap
COMPOSIO_* tools inside `agentnet mcp-serve`, and they never store third-party
OAuth tokens. Skip the merge when the user already has a `composio` server, and
disconnect only removes an entry this CLI added.

Official plugin shape (ComposioHQ/composio-mcp-plugin):

    {"mcpServers": {"composio": {"url": "https://connect.composio.dev/mcp"}}}

Set ``AGENTNET_COMPOSIO_MCP=0`` to disable the merge.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

COMPOSIO_SERVER_NAME = "composio"
COMPOSIO_MCP_URL = "https://connect.composio.dev/mcp"
COMPOSIO_ENV_DISABLE = "AGENTNET_COMPOSIO_MCP"

_DISABLE_VALUES = frozenset({"0", "false", "no", "off"})


def composio_enabled() -> bool:
    raw = os.environ.get(COMPOSIO_ENV_DISABLE, "1").strip().lower()
    return raw not in _DISABLE_VALUES


def composio_http_entry() -> dict[str, str]:
    return {"url": COMPOSIO_MCP_URL}


def merge_mapping(servers: dict[str, Any]) -> bool:
    """Insert the Composio HTTP MCP entry. Return True if this CLI added it."""
    if not composio_enabled():
        return False
    if COMPOSIO_SERVER_NAME in servers:
        return False
    servers[COMPOSIO_SERVER_NAME] = composio_http_entry()
    return True


def unmerge_mapping(servers: Any, *, owned: bool) -> None:
    """Remove `composio` only when this CLI added it during connect."""
    if owned and isinstance(servers, dict):
        servers.pop(COMPOSIO_SERVER_NAME, None)


def stamp(
    mcp_entry: dict[str, Any],
    *,
    owned: bool,
    file: str | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Record Composio ownership on the connector's mcp_entry (manifest)."""
    info: dict[str, Any] = {"owned": owned}
    if file is not None:
        info["file"] = file
    if files is not None:
        info["files"] = files
    mcp_entry["composio"] = info
    return mcp_entry


def composio_owned(mcp_info: dict[str, Any] | None) -> bool:
    if not mcp_info:
        return False
    composio = mcp_info.get("composio")
    return bool(isinstance(composio, dict) and composio.get("owned"))


def merge_json_file(path: Path, *, servers_key: str) -> bool:
    """Merge Composio into a JSON MCP file. Return True if this CLI added it.

    Malformed JSON is left untouched (not owned).
    """
    if not composio_enabled():
        return False
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return False
        if not isinstance(loaded, dict):
            return False
        data = loaded
    servers = data.setdefault(servers_key, {})
    if not isinstance(servers, dict):
        return False
    owned = merge_mapping(servers)
    if owned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
    return owned


def unmerge_json_file(path: Path, *, servers_key: str, owned: bool) -> None:
    if not owned or not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    unmerge_mapping(data.get(servers_key), owned=True)
    try:
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError:
        return
