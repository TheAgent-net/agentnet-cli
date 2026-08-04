"""Codex connector for MCP server config and skill files."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from ..infra.paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


class CodexConnector(AgentConnector):
    """Connect Codex through MCP config and an AgentNet skill file."""

    def detect(self) -> DetectionResult:
        """Detect Codex config in this environment."""
        root = agent_config_root(AgentName.CODEX, self.env)
        base = DetectionResult(
            agent_name=AgentName.CODEX,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )
        if not root.exists():
            return base
        for vf in ["config.toml", "auth.json"]:
            if (root / vf).exists():
                return DetectionResult(
                    agent_name=AgentName.CODEX,
                    detected=True,
                    config_root=root,
                    env_key=self.env.key,
                    env_label=self.env.label,
                )
        return base

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Write MCP config and install the AgentNet Codex skill file."""
        files_created: list[Path] = []
        root = agent_config_root(AgentName.CODEX, self.env)
        root.mkdir(parents=True, exist_ok=True)

        toml_path = root / "config.toml"
        data: dict[str, Any] = {}
        if toml_path.exists():
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))

        from .mcp_entry import make_mcp_server_entry

        entry = make_mcp_server_entry(
            self.env,
            env_vars={"AGENTNET_TOKEN": "${AGENTNET_TOKEN}"},
        )
        # Only uvx needs an explicit token env placeholder; PATH installs inherit.
        use_uvx = entry["command"] == "uvx"
        mcp_servers = data.setdefault("mcp_servers", {})
        agentnet_entry: dict[str, Any] = {
            "default_tools_approval_mode": "auto",
            "command": entry["command"],
            "args": entry["args"],
        }
        if use_uvx:
            agentnet_entry["env"] = entry["env"]
        mcp_servers["agentnet"] = agentnet_entry
        toml_path.write_text(tomli_w.dumps(data), encoding="utf-8")

        skill_dir = root / "skills" / "agentnet"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(load_shim("codex/skill.md"), encoding="utf-8")
        files_created.append(skill_path)
        return ConnectionResult(
            success=True, files_created=files_created,
            mcp_entry={"scope": "user", "file": str(toml_path), "server_name": "agentnet"},
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Remove skill files and the AgentNet MCP entry from Codex config."""
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()
        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if mcp_file:
            toml_path = Path(mcp_file)
            if toml_path.exists():
                data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                data.get("mcp_servers", {}).pop("agentnet", None)
                toml_path.write_text(tomli_w.dumps(data), encoding="utf-8")
        return True
