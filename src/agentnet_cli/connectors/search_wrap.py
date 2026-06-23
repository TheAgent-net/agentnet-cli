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


class SearchWrapError(Exception):
    pass


def _proxy_entry(upstream: str, agent: AgentName) -> dict[str, Any]:
    """The MCP server entry that launches the AgentNet proxy for an upstream.

    The proxy resolves its AgentNet token from ``AGENTNET_TOKEN`` in the
    environment, falling back to ``~/.agentnet/config.json`` (see
    ``load_agentnet_credentials``). Only Cursor/VS Code expand the
    ``${env:VAR}`` interpolation syntax in an MCP ``env`` block, so we set it
    only for Cursor. Claude and Codex do **not** expand it — passing the literal
    string would authenticate with garbage and silently fail every call — so we
    omit ``env`` entirely for them and rely on the config-file fallback (the same
    approach their own connectors use for the installed-binary path).
    """
    agentnet_bin = shutil.which("agentnet")
    if agentnet_bin:
        command, args = agentnet_bin, ["mcp-proxy", "--upstream", upstream]
    else:
        command, args = "uvx", ["agentnet-cli", "mcp-proxy", "--upstream", upstream]
    entry: dict[str, Any] = {"command": command, "args": args}
    if agent == AgentName.CURSOR:
        entry["env"] = {"AGENTNET_TOKEN": "${env:AGENTNET_TOKEN}"}
    return entry


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
#
# We stash the ORIGINAL RAW FILE TEXT (not just the parsed entry) so unwrap can
# restore the config byte-for-byte. This matters for TOML especially: a
# parse->serialize round-trip via tomllib + tomli_w silently drops comments and
# normalises formatting, so re-emitting the parsed dict on unwrap could never
# recover a user's annotations. Storing raw text makes the byte-for-byte restore
# guarantee hold for every agent.


def _stash(agent: str, server_name: str, original_text: str) -> None:
    m = load_manifest()
    wraps = m.setdefault("search_wraps", {})
    wraps[agent] = {"server_name": server_name, "original_text": original_text}
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


def _wrap_json(path: Path, agent: AgentName, upstream: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"no config at {path}"
    original_text = path.read_text()
    data = json.loads(original_text)
    servers = data.get("mcpServers", {})
    for name, entry in servers.items():
        if isinstance(entry, dict) and _is_upstream_entry(name, entry, upstream):
            if _is_already_wrapped(entry):
                return False, f"{name} already wrapped"
            _stash(agent.value, name, original_text)
            servers[name] = _proxy_entry(upstream, agent)
            path.write_text(json.dumps(data, indent=2) + "\n")
            return True, name
    return False, f"no {upstream} MCP entry found in {path.name}"


def _wrap_toml(path: Path, agent: AgentName, upstream: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"no config at {path}"
    original_text = path.read_text()
    data = tomllib.loads(original_text)
    servers = data.get("mcp_servers", {})
    for name, entry in servers.items():
        if isinstance(entry, dict) and _is_upstream_entry(name, entry, upstream):
            if _is_already_wrapped(entry):
                return False, f"{name} already wrapped"
            _stash(agent.value, name, original_text)
            servers[name] = _proxy_entry(upstream, agent)
            path.write_text(tomli_w.dumps(data))
            return True, name
    return False, f"no {upstream} MCP entry found in {path.name}"


def _restore_raw(path: Path, stash: dict[str, Any]) -> bool:
    """Restore the original config text byte-for-byte from the stash."""
    if not path.exists():
        return False
    path.write_text(stash["original_text"])
    return True


# -- public surface --


def _config_path(agent: AgentName) -> Path:
    if agent == AgentName.CODEX:
        return agent_config_root(AgentName.CODEX) / "config.toml"
    return _json_config_path(agent)


def wrap(agent: AgentName, upstream: str) -> tuple[bool, str]:
    """Wrap an agent's search-provider entry. Returns (changed, message)."""
    if agent == AgentName.CODEX:
        return _wrap_toml(_config_path(agent), agent, upstream)
    if agent in (AgentName.CURSOR, AgentName.CLAUDE):
        return _wrap_json(_config_path(agent), agent, upstream)
    raise SearchWrapError(f"{agent} is not supported for search wrapping")


def unwrap(agent: AgentName) -> tuple[bool, str]:
    """Restore an agent's original search-provider entry. Returns (changed, message)."""
    stash = _unstash(agent.value)
    if not stash:
        return False, "nothing wrapped"
    if _restore_raw(_config_path(agent), stash):
        _clear_stash(agent.value)
        return True, stash["server_name"]
    return False, "config missing; stash kept"


def manual_block(upstream: str, agent: AgentName = AgentName.CURSOR) -> str:
    """Return the MCP entry JSON to paste in place of the search provider."""
    return json.dumps({upstream: _proxy_entry(upstream, agent)}, indent=2)
