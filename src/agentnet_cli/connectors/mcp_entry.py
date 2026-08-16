"""Make the MCP stdio server entry for all connectors."""

from __future__ import annotations

from typing import Any

from ..infra.environments import Environment
from ..infra.proc import find_executable


def make_mcp_server_entry(
    env: Environment,
    *,
    env_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make an MCP server entry: ``{command, args, env?}``.

    On a local host, use ``agentnet`` on PATH or ``uvx agentnet-cli``.
    On other hosts, use :meth:`Environment.mcp_command`.
    """
    if env.kind == "local":
        agentnet_bin = find_executable("agentnet")
        if agentnet_bin:
            command, args = agentnet_bin, ["mcp-serve"]
        else:
            command, args = "uvx", ["agentnet-cli", "mcp-serve"]
    else:
        command, args = env.mcp_command()

    entry: dict[str, Any] = {"command": command, "args": args}
    if env_vars:
        entry["env"] = env_vars
    return entry
