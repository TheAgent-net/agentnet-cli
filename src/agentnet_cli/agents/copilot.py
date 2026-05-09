from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


class CopilotConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.COPILOT)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.COPILOT, detected=False)
        if any((root / vf).exists() for vf in ["settings.json", "config.json", "mcp-config.json", "ide"]):
            return DetectionResult(agent_name=AgentName.COPILOT, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.COPILOT, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        files_created: list[Path] = []

        root = agent_config_root(AgentName.COPILOT)
        root.mkdir(parents=True, exist_ok=True)

        dot_mcp = root / "mcp-config.json"
        mcp_entry_info = self._merge_mcp(dot_mcp, self._build_mcp_entry())

        agents_dir = root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "agentnet.agent.md"
        agent_path.write_text(load_shim("copilot/agentnet.agent.md"))
        files_created.append(agent_path)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            mcp_entry=mcp_entry_info,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        deleted: list[Path] = []
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()
                deleted.append(p)

        # Clean empty parent dirs (e.g. agents/)
        for p in deleted:
            if p.parent.exists() and not any(p.parent.iterdir()):
                p.parent.rmdir()

        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if mcp_file:
            mcp_path = Path(mcp_file)
            if mcp_path.exists():
                data = json.loads(mcp_path.read_text())
                data.get("mcpServers", {}).pop("agentnet", None)
                mcp_path.write_text(json.dumps(data, indent=2) + "\n")

        return True

    def _build_mcp_entry(self) -> dict[str, Any]:
        agentnet_bin = shutil.which("agentnet")
        if agentnet_bin:
            return {
                "type": "stdio",
                "command": agentnet_bin,
                "args": ["mcp-serve"],
            }
        return {
            "type": "stdio",
            "command": "uvx",
            "args": ["agentnet-cli", "mcp-serve"],
        }

    def _merge_mcp(self, mcp_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
        data.setdefault("mcpServers", {})
        data["mcpServers"]["agentnet"] = entry
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(json.dumps(data, indent=2) + "\n")
        return {"scope": "user", "file": str(mcp_path), "server_name": "agentnet"}
