from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import tomli_w

from ..infra.paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


class CodexConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.CODEX)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.CODEX, detected=False)
        for vf in ["config.toml", "auth.json"]:
            if (root / vf).exists():
                return DetectionResult(agent_name=AgentName.CODEX, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.CODEX, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        files_created: list[Path] = []
        root = agent_config_root(AgentName.CODEX)
        root.mkdir(parents=True, exist_ok=True)

        toml_path = root / "config.toml"
        data: dict[str, Any] = {}
        if toml_path.exists():
            data = tomllib.loads(toml_path.read_text())

        agentnet_bin = shutil.which("agentnet")
        if agentnet_bin:
            command = agentnet_bin
        else:
            command = "uvx"

        mcp_servers = data.setdefault("mcp_servers", {})
        agentnet_entry: dict[str, Any] = {"default_tools_approval_mode": "auto"}
        if command == "uvx":
            agentnet_entry.update({
                "command": command,
                "args": ["agentnet-cli", "mcp-serve"],
                "env": {"AGENTNET_TOKEN": "${AGENTNET_TOKEN}"},
            })
        else:
            agentnet_entry.update({
                "command": command,
                "args": ["mcp-serve"],
            })
        mcp_servers["agentnet"] = agentnet_entry
        toml_path.write_text(tomli_w.dumps(data))

        skill_dir = root / "skills" / "agentnet"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(load_shim("codex/skill.md"))
        files_created.append(skill_path)
        return ConnectionResult(
            success=True, files_created=files_created,
            mcp_entry={"scope": "user", "file": str(toml_path), "server_name": "agentnet"},
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()
        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if mcp_file:
            toml_path = Path(mcp_file)
            if toml_path.exists():
                data = tomllib.loads(toml_path.read_text())
                data.get("mcp_servers", {}).pop("agentnet", None)
                toml_path.write_text(tomli_w.dumps(data))
        return True
