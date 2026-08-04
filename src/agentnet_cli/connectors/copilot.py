"""GitHub Copilot connector for MCP config, agent file, and instructions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..infra.paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


class CopilotConnector(AgentConnector):
    """Connect Copilot through MCP config, agent file, and instructions."""

    def detect(self) -> DetectionResult:
        """Detect Copilot config in this environment."""
        root = agent_config_root(AgentName.COPILOT, self.env)
        if not root.exists():
            return DetectionResult(
                agent_name=AgentName.COPILOT,
                detected=False,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        if any(
            (root / vf).exists()
            for vf in ["settings.json", "config.json", "mcp-config.json", "ide"]
        ):
            return DetectionResult(
                agent_name=AgentName.COPILOT,
                detected=True,
                config_root=root,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        return DetectionResult(
            agent_name=AgentName.COPILOT,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Write MCP config, agent file, and Copilot instructions."""
        files_created: list[Path] = []

        root = agent_config_root(AgentName.COPILOT, self.env)
        root.mkdir(parents=True, exist_ok=True)

        dot_mcp = root / "mcp-config.json"
        mcp_entry_info = self._merge_mcp(dot_mcp, self._build_mcp_entry())

        agents_dir = root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "agentnet.agent.md"
        agent_path.write_text(load_shim("copilot/agentnet.agent.md"), encoding="utf-8")
        files_created.append(agent_path)

        instructions_path = root / "copilot-instructions.md"
        instructions_path.write_text(load_shim("shared/default-chat.md"), encoding="utf-8")
        files_created.append(instructions_path)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            mcp_entry=mcp_entry_info,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Remove created files and the AgentNet MCP entry from Copilot config."""
        deleted: list[Path] = []
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()
                deleted.append(p)

        for p in deleted:
            if p.parent.exists() and not any(p.parent.iterdir()):
                p.parent.rmdir()

        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if mcp_file:
            mcp_path = Path(mcp_file)
            if mcp_path.exists():
                data = json.loads(mcp_path.read_text(encoding="utf-8"))
                data.get("mcpServers", {}).pop("agentnet", None)
                mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        return True

    def _build_mcp_entry(self) -> dict[str, Any]:
        from .mcp_entry import make_mcp_server_entry

        entry = make_mcp_server_entry(self.env)
        entry["type"] = "stdio"
        return entry

    def _merge_mcp(self, mcp_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
        from ..infra.config import write_file_safe

        data: dict[str, Any] = {}
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        data.setdefault("mcpServers", {})
        data["mcpServers"]["agentnet"] = entry
        write_file_safe(mcp_path, json.dumps(data, indent=2) + "\n")
        return {"scope": "user", "file": str(mcp_path), "server_name": "agentnet"}
