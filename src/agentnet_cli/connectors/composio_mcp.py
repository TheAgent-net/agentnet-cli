"""Register Composio Connect as a sibling HTTP MCP server.

AgentNet is the discovery layer (stdio `agentnet` MCP). Composio is the action
layer for GitHub, Slack, Linear, and 1000+ other apps. Connectors merge a
`composio` entry pointing at https://connect.composio.dev/mcp — they never wrap
COMPOSIO_* tools inside `agentnet mcp-serve`, and they never store third-party
OAuth tokens. Skip the merge when the user already has a `composio` server, and
disconnect only removes an entry this CLI added *and* that still matches our URL.

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


def is_our_entry(value: Any) -> bool:
    """True when the MCP entry is still the URL this CLI inserted."""
    return isinstance(value, dict) and value.get("url") == COMPOSIO_MCP_URL


def merge_mapping(servers: dict[str, Any], *, previously_owned: bool = False) -> bool:
    """Insert the Composio HTTP MCP entry. Return True if this CLI owns it.

    Reconnect: if we previously owned the key and it still matches our URL,
    keep ownership so a later disconnect can remove it. A user-replaced URL
    is not ours, even if the manifest still said owned.
    """
    if not composio_enabled():
        return False
    existing = servers.get(COMPOSIO_SERVER_NAME)
    if existing is None:
        servers[COMPOSIO_SERVER_NAME] = composio_http_entry()
        return True
    return previously_owned and is_our_entry(existing)


def unmerge_mapping(servers: Any, *, owned: bool) -> None:
    """Remove `composio` only when we added it and it still matches our URL."""
    if not owned or not isinstance(servers, dict):
        return
    if is_our_entry(servers.get(COMPOSIO_SERVER_NAME)):
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


def prior_owned(agent_name: str) -> bool:
    """Whether a recorded connection for this agent still owns `composio`."""
    from ..infra.manifest import load_manifest

    conn = load_manifest().get("connections", {}).get(agent_name, {})
    return composio_owned(conn.get("mcp_registered"))


def prior_owned_files(agent_name: str) -> set[str]:
    """Absolute paths where a previous connect recorded a CLI-owned composio."""
    from ..infra.manifest import load_manifest

    conn = load_manifest().get("connections", {}).get(agent_name, {})
    info = (conn.get("mcp_registered") or {}).get("composio") or {}
    if not isinstance(info, dict) or not info.get("owned"):
        return set()
    files = {str(p) for p in info.get("files") or [] if p}
    if info.get("file"):
        files.add(str(info["file"]))
    return files


def merge_json_file(
    path: Path, *, servers_key: str, previously_owned: bool = False,
) -> bool:
    """Merge Composio into a JSON MCP file. Return True if this CLI owns it.

    Malformed JSON and write failures are left untouched (not owned).
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
    had_key = COMPOSIO_SERVER_NAME in servers
    owned = merge_mapping(servers, previously_owned=previously_owned)
    if owned and not had_key:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n")
        except OSError:
            servers.pop(COMPOSIO_SERVER_NAME, None)
            return False
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
