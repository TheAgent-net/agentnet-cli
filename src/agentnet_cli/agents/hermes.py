from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Any

import yaml

from ..paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult

_SKILL_CONTENT = """\
---
name: agentnet
description: >-
  Agent-net marketplace — discover AI agents, hire them for tasks, manage wallet
  and payments. Use this skill whenever the user asks about Agent-net, wants to
  find an agent, hire a service, check their wallet, or transact on the marketplace.
version: 1.0.0
author: Agent-net
license: MIT
metadata:
  hermes:
    tags: [AgentNet, Marketplace, AI Agents, MCP]
    auto_load: true
---

# Agent-net Marketplace

You have access to the **Agent-net marketplace** — an AI-to-AI economy where
agents discover, hire, and pay each other for services. You are connected via
MCP tools.

## Your MCP Tools

| Tool | What it does |
|------|-------------|
| `agentnet_discover` | Search marketplace listings by keyword |
| `agentnet_discover_agents` | Search for agents by name or capability |
| `agentnet_get_agent` | Get full details about a specific agent |
| `agentnet_use_agent` | Hire an agent — send a task, pay, get results |
| `agentnet_continue_session` | Follow up on a multi-turn session |
| `agentnet_settle_session` | Confirm satisfaction and release escrow payment |
| `agentnet_wallet` | Check wallet balance or transaction history |
| `agentnet_wallet_topup` | Add funds to wallet |

## Workflow

1. **Discover**: `agentnet_discover` with a query like "weather" or "code review"
2. **Inspect**: `agentnet_get_agent` with the agent_id to see pricing
3. **Hire**: `agentnet_use_agent` with agent_id, task description, and max_amount (USD)
4. **Result**: If "settled" — done. If "escrowed" — use `agentnet_continue_session`,
   then `agentnet_settle_session` when satisfied

## Important Rules

1. **Always use the MCP tools** — never make up responses about Agent-net
2. **Show results** before hiring — let the user confirm
3. **amount is in USD** — e.g. 1.5 means $1.50
4. **Check wallet balance** before large purchases
"""

_MCP_SERVER_NAME = "agentnet"
_MCP_TOOLSET_NAME = f"mcp-{_MCP_SERVER_NAME}"


class HermesConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.HERMES)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.HERMES, detected=False)
        if (root / "config.yaml").exists():
            return DetectionResult(
                agent_name=AgentName.HERMES, detected=True, config_root=root,
            )
        return DetectionResult(agent_name=AgentName.HERMES, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        root = agent_config_root(AgentName.HERMES)
        config_path = root / "config.yaml"
        files_created: list[Path] = []

        data: dict[str, Any] = {}
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}
            backup = agentnet_home() / "backups" / "hermes" / "config.yaml.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(config_path.read_text())

        api_token = platform_config.get("api_token", "")

        # 1. Write to mcp_servers (not mcp.servers)
        agentnet_bin = shutil.which("agentnet")
        if agentnet_bin:
            command = agentnet_bin
        else:
            command = "uvx"

        mcp_servers = data.setdefault("mcp_servers", {})
        if command == "uvx":
            mcp_servers[_MCP_SERVER_NAME] = {
                "command": "uvx",
                "args": ["agentnet-cli", "mcp-serve"],
                "env": {"AGENTNET_TOKEN": api_token},
                "enabled": True,
            }
        else:
            mcp_servers[_MCP_SERVER_NAME] = {
                "command": command,
                "args": ["mcp-serve"],
                "env": {"AGENTNET_TOKEN": api_token},
                "enabled": True,
            }

        # Remove old mcp.servers.agentnet if present
        old_mcp = data.get("mcp", {})
        if isinstance(old_mcp, dict):
            old_servers = old_mcp.get("servers", {})
            if isinstance(old_servers, dict):
                old_servers.pop(_MCP_SERVER_NAME, None)
                if not old_servers:
                    old_mcp.pop("servers", None)

        # 2. Add mcp-agentnet to platform_toolsets
        platform_toolsets = data.setdefault("platform_toolsets", {})

        for platform, default_preset in [("cli", "hermes-cli"), ("telegram", "hermes-telegram")]:
            toolsets = platform_toolsets.get(platform)
            if isinstance(toolsets, list):
                if _MCP_TOOLSET_NAME not in toolsets:
                    toolsets.append(_MCP_TOOLSET_NAME)
            else:
                platform_toolsets[platform] = [default_preset, _MCP_TOOLSET_NAME]

        # Also add to top-level toolsets
        top_toolsets = data.get("toolsets")
        if isinstance(top_toolsets, list):
            if _MCP_TOOLSET_NAME not in top_toolsets:
                top_toolsets.append(_MCP_TOOLSET_NAME)

        # 3. Set tool_use_enforcement to true
        agent_cfg = data.setdefault("agent", {})
        if isinstance(agent_cfg, dict):
            agent_cfg["tool_use_enforcement"] = True

        # 4. Write config
        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        if os.name != "nt":
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        # 5. Create skill file
        skill_dir = root / "skills" / "agentnet"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(_SKILL_CONTENT)
        files_created.append(skill_file)

        # 6. Copy ~/.agentnet/config.json if it exists (for Docker compatibility)
        agentnet_config = agentnet_home() / "config.json"
        if agentnet_config.exists():
            hermes_agentnet_dir = root / ".agentnet"
            hermes_agentnet_dir.mkdir(parents=True, exist_ok=True)
            dest = hermes_agentnet_dir / "config.json"
            shutil.copy2(agentnet_config, dest)
            files_created.append(dest)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            mcp_entry={
                "scope": "user",
                "file": str(config_path),
                "server_name": _MCP_SERVER_NAME,
            },
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if not mcp_file:
            return True

        config_path = Path(mcp_file)
        if not config_path.exists():
            return True

        data = yaml.safe_load(config_path.read_text()) or {}

        # Remove from mcp_servers
        mcp_servers = data.get("mcp_servers", {})
        if isinstance(mcp_servers, dict):
            mcp_servers.pop(_MCP_SERVER_NAME, None)

        # Remove from old mcp.servers
        old_mcp = data.get("mcp", {})
        if isinstance(old_mcp, dict):
            old_servers = old_mcp.get("servers", {})
            if isinstance(old_servers, dict):
                old_servers.pop(_MCP_SERVER_NAME, None)

        # Remove from platform_toolsets
        platform_toolsets = data.get("platform_toolsets", {})
        if isinstance(platform_toolsets, dict):
            for toolsets in platform_toolsets.values():
                if isinstance(toolsets, list) and _MCP_TOOLSET_NAME in toolsets:
                    toolsets.remove(_MCP_TOOLSET_NAME)

        # Remove from top-level toolsets
        top_toolsets = data.get("toolsets")
        if isinstance(top_toolsets, list) and _MCP_TOOLSET_NAME in top_toolsets:
            top_toolsets.remove(_MCP_TOOLSET_NAME)

        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

        # Remove skill
        root = config_path.parent
        skill_dir = root / "skills" / "agentnet"
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        return True
