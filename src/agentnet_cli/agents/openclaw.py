from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult

_CLAWHUB_PACKAGE = "clawhub:agentnet"
_PLUGIN_ID = "agentnet"
_MCP_SERVER_NAME = "agentnet"
_MCP_SERVER_CONFIG = '{"command":"agentnet","args":["mcp-serve"]}'
_SUBPROCESS_TIMEOUT = 120


def _find_plugin_source() -> str:
    local = Path(__file__).resolve().parent.parent.parent.parent
    if (local / "openclaw-plugin" / "openclaw.plugin.json").exists():
        return str(local / "openclaw-plugin")
    return _CLAWHUB_PACKAGE


class OpenClawConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.OPENCLAW)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.OPENCLAW, detected=False)
        if (root / "openclaw.json").exists():
            return DetectionResult(agent_name=AgentName.OPENCLAW, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.OPENCLAW, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        openclaw_bin = shutil.which("openclaw")
        if not openclaw_bin:
            return ConnectionResult(
                success=False,
                errors=["OpenClaw not found. Install it from https://docs.openclaw.ai"],
            )

        plugin_source = _find_plugin_source()

        proc = subprocess.run(
            ["openclaw", "plugins", "install", plugin_source, "--force"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if proc.returncode != 0:
            msg = proc.stderr.decode(errors="replace").strip()
            return ConnectionResult(success=False, errors=[f"plugin install failed: {msg}"])

        proc = subprocess.run(
            ["openclaw", "mcp", "set", _MCP_SERVER_NAME, _MCP_SERVER_CONFIG],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if proc.returncode != 0:
            msg = proc.stderr.decode(errors="replace").strip()
            return ConnectionResult(success=False, errors=[f"mcp set failed: {msg}"])

        self._cleanup_legacy()

        return ConnectionResult(
            success=True,
            mcp_entry={"scope": "plugin", "plugin_id": _PLUGIN_ID},
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        openclaw_bin = shutil.which("openclaw")
        if not openclaw_bin:
            return True

        subprocess.run(
            ["openclaw", "mcp", "unset", _MCP_SERVER_NAME],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        subprocess.run(
            ["openclaw", "plugins", "uninstall", _PLUGIN_ID, "--force"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        return True

    @staticmethod
    def _cleanup_legacy() -> None:
        root = agent_config_root(AgentName.OPENCLAW)

        config_path = root / "openclaw.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                if "agentnet-gateway" in data.get("plugins", {}):
                    data["plugins"].pop("agentnet-gateway")
                    config_path.write_text(json.dumps(data, indent=2) + "\n")
            except (json.JSONDecodeError, OSError):
                pass

        backup = agentnet_home() / "backups" / "openclaw" / "openclaw.json.bak"
        if backup.exists():
            try:
                backup.unlink()
                backup_dir = backup.parent
                if backup_dir.exists() and not any(backup_dir.iterdir()):
                    backup_dir.rmdir()
            except OSError:
                pass
