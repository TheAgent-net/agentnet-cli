from __future__ import annotations
import json
import os
import stat
from pathlib import Path
from typing import Any
from ..paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult


class OpenClawConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.OPENCLAW)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.OPENCLAW, detected=False)
        if (root / "openclaw.json").exists():
            return DetectionResult(agent_name=AgentName.OPENCLAW, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.OPENCLAW, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        root = agent_config_root(AgentName.OPENCLAW)
        config_path = root / "openclaw.json"
        data: dict[str, Any] = {}
        if config_path.exists():
            data = json.loads(config_path.read_text())
            backup = agentnet_home() / "backups" / "openclaw" / "openclaw.json.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(config_path.read_bytes())
        plugins = data.setdefault("plugins", {})
        plugins["agentnet-gateway"] = {
            "enabled": True,
            "config": {
                "platformUrl": platform_config.get("platform_url", ""),
                "platformToken": platform_config.get("api_token", ""),
            },
        }
        config_path.write_text(json.dumps(data, indent=2) + "\n")
        if os.name != "nt":
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return ConnectionResult(
            success=True,
            mcp_entry={"scope": "user", "file": str(config_path), "server_name": "agentnet-gateway"},
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if mcp_file:
            config_path = Path(mcp_file)
            if config_path.exists():
                data = json.loads(config_path.read_text())
                data.get("plugins", {}).pop("agentnet-gateway", None)
                config_path.write_text(json.dumps(data, indent=2) + "\n")
        return True
