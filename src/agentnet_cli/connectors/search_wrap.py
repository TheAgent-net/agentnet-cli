"""Route a search provider's MCP entry through the AgentNet proxy.

``wrap`` finds an agent's existing search-provider MCP server (Exa, Parallel),
stashes its original config in the manifest, and rewrites the entry to launch
``agentnet mcp-proxy`` instead — so every search fires AgentNet alongside it.
``unwrap`` restores the original entry byte-for-byte from the manifest.

Supports Cursor (``~/.cursor/mcp.json``), Codex (``~/.codex/config.toml``), and
Claude (``~/.claude.json``). Operations are idempotent: re-wrapping a wrapped
entry is a no-op, and unwrapping with nothing stashed is a no-op.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import tomli_w
import tomllib

from ..infra.manifest import load_manifest, save_manifest
from ..infra.paths import AgentName, agent_config_root

UPSTREAM_URL_HINTS = {
    "exa": ("mcp.exa.ai",),
    "parallel": ("search.parallel.ai", "parallel.ai"),
}

SUPPORTED_AGENTS = (AgentName.CURSOR, AgentName.CODEX, AgentName.CLAUDE)


class SearchWrapError(Exception):
    pass


def _proxy_entry(upstream: str) -> dict[str, Any]:
    """The MCP server entry that launches the AgentNet proxy for an upstream."""
    agentnet_bin = shutil.which("agentnet")
    if agentnet_bin:
        command, args = agentnet_bin, ["mcp-proxy", "--upstream", upstream]
    else:
        command, args = "uvx", ["agentnet-cli", "mcp-proxy", "--upstream", upstream]
    return {
        "command": command,
        "args": args,
        "env": {"AGENTNET_TOKEN": "${env:AGENTNET_TOKEN}"},
    }


def _is_upstream_entry(name: str, entry: dict[str, Any], upstream: str) -> bool:
    """Heuristic: does this MCP entry point at the given search provider?"""
    hints = UPSTREAM_URL_HINTS.get(upstream, ())
    blob = json.dumps(entry).lower()
    if name.lower() == upstream or any(h in blob for h in hints):
        return True
    return False


def _is_already_wrapped(entry: dict[str, Any]) -> bool:
    return "mcp-proxy" in json.dumps(entry)


# -- manifest stash --


def _stash(agent: str, server_name: str, original: dict[str, Any]) -> None:
    m = load_manifest()
    wraps = m.setdefault("search_wraps", {})
    wraps[agent] = {"server_name": server_name, "original": original}
    save_manifest(m)


def _unstash(agent: str) -> dict[str, Any] | None:
    m = load_manifest()
    wraps = m.get("search_wraps", {})
    return wraps.get(agent)


def _clear_stash(agent: str) -> None:
    m = load_manifest()
    wraps = m.get("search_wraps", {})
    if agent in wraps:
        del wraps[agent]
        save_manifest(m)


# -- per-format JSON/TOML helpers (Cursor + Claude are JSON, Codex is TOML) --


def _json_config_path(agent: AgentName) -> Path:
    if agent == AgentName.CURSOR:
        return agent_config_root(AgentName.CURSOR) / "mcp.json"
    if agent == AgentName.CLAUDE:
        return agent_config_root(AgentName.CLAUDE).parent / ".claude.json"
    raise SearchWrapError(f"{agent} is not a JSON-config agent")


def _wrap_json(path: Path, agent: str, upstream: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"no config at {path}"
    data = json.loads(path.read_text())
    servers = data.get("mcpServers", {})
    for name, entry in servers.items():
        if isinstance(entry, dict) and _is_upstream_entry(name, entry, upstream):
            if _is_already_wrapped(entry):
                return False, f"{name} already wrapped"
            _stash(agent, name, entry)
            servers[name] = _proxy_entry(upstream)
            path.write_text(json.dumps(data, indent=2) + "\n")
            return True, name
    return False, f"no {upstream} MCP entry found in {path.name}"


def _unwrap_json(path: Path, agent: str, stash: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    servers = data.setdefault("mcpServers", {})
    servers[stash["server_name"]] = stash["original"]
    path.write_text(json.dumps(data, indent=2) + "\n")
    return True


def _wrap_toml(path: Path, agent: str, upstream: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"no config at {path}"
    data = tomllib.loads(path.read_text())
    servers = data.get("mcp_servers", {})
    for name, entry in servers.items():
        if isinstance(entry, dict) and _is_upstream_entry(name, entry, upstream):
            if _is_already_wrapped(entry):
                return False, f"{name} already wrapped"
            _stash(agent, name, entry)
            servers[name] = _proxy_entry(upstream)
            path.write_text(tomli_w.dumps(data))
            return True, name
    return False, f"no {upstream} MCP entry found in {path.name}"


def _unwrap_toml(path: Path, agent: str, stash: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    data = tomllib.loads(path.read_text())
    servers = data.setdefault("mcp_servers", {})
    servers[stash["server_name"]] = stash["original"]
    path.write_text(tomli_w.dumps(data))
    return True


# -- public surface --


def wrap(agent: AgentName, upstream: str) -> tuple[bool, str]:
    """Wrap an agent's search-provider entry. Returns (changed, message)."""
    if agent == AgentName.CODEX:
        return _wrap_toml(agent_config_root(AgentName.CODEX) / "config.toml", agent.value, upstream)
    if agent in (AgentName.CURSOR, AgentName.CLAUDE):
        return _wrap_json(_json_config_path(agent), agent.value, upstream)
    raise SearchWrapError(f"{agent} is not supported for search wrapping")


def unwrap(agent: AgentName) -> tuple[bool, str]:
    """Restore an agent's original search-provider entry. Returns (changed, message)."""
    stash = _unstash(agent.value)
    if not stash:
        return False, "nothing wrapped"
    if agent == AgentName.CODEX:
        ok = _unwrap_toml(agent_config_root(AgentName.CODEX) / "config.toml", agent.value, stash)
    else:
        ok = _unwrap_json(_json_config_path(agent), agent.value, stash)
    if ok:
        _clear_stash(agent.value)
        return True, stash["server_name"]
    return False, "config missing; stash kept"


def manual_block(upstream: str) -> str:
    """Return the MCP entry JSON to paste in place of the search provider."""
    return json.dumps({_proxy_label(upstream): _proxy_entry(upstream)}, indent=2)


def _proxy_label(upstream: str) -> str:
    return upstream
