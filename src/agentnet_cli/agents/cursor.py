from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


class CursorConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.CURSOR)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.CURSOR, detected=False)
        for vf in ["extensions", "mcp.json", "cli-config.json"]:
            if (root / vf).exists():
                return DetectionResult(agent_name=AgentName.CURSOR, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.CURSOR, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        files_created: list[Path] = []
        root = agent_config_root(AgentName.CURSOR)

        # Layer 1: MCP
        mcp_path = root / "mcp.json"
        mcp_entry = self._write_mcp(mcp_path)

        # Layer 2a: Rule
        rules_dir = root / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        mdc_path = rules_dir / "agentnet.mdc"
        mdc_path.write_text(load_shim("cursor/agentnet.mdc"))
        files_created.append(mdc_path)

        # Layer 2b: Subagent
        agents_dir = root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "agentnet.md"
        agent_path.write_text(load_shim("cursor/agent.md"))
        files_created.append(agent_path)

        return ConnectionResult(
            success=True, files_created=files_created, mcp_entry=mcp_entry,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        deleted: list[Path] = []
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()
                deleted.append(p)

        # Clean empty parent dirs (e.g. rules/, agents/)
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

    def _write_mcp(self, mcp_path: Path) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
        data.setdefault("mcpServers", {})

        agentnet_bin = shutil.which("agentnet")
        if agentnet_bin:
            command, args = agentnet_bin, ["mcp-serve"]
        else:
            command, args = "uvx", ["agentnet-cli", "mcp-serve"]

        data["mcpServers"]["agentnet"] = {
            "command": command,
            "args": args,
            "env": {"AGENTNET_TOKEN": "${env:AGENTNET_TOKEN}"},
        }
        mcp_path.write_text(json.dumps(data, indent=2) + "\n")
        return {"scope": "global", "file": str(mcp_path), "server_name": "agentnet"}
