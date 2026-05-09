from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult

_MARKETPLACE = "TheAgent-net/agentnet-cli"
_PLUGIN_ID = "agentnet@agentnet-cli"
_SUBPROCESS_TIMEOUT = 120


class ClaudeConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.CLAUDE)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.CLAUDE, detected=False)
        for vf in ["settings.json"]:
            if (root / vf).exists():
                return DetectionResult(agent_name=AgentName.CLAUDE, detected=True, config_root=root)
        claude_json = root.parent / ".claude.json"
        if claude_json.exists():
            return DetectionResult(agent_name=AgentName.CLAUDE, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.CLAUDE, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            return ConnectionResult(
                success=False,
                errors=["Claude Code not found. Install it from https://code.claude.com"],
            )

        proc = subprocess.run(
            ["claude", "plugin", "marketplace", "add", _MARKETPLACE, "--scope", "user"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if proc.returncode != 0:
            msg = proc.stderr.decode(errors="replace").strip()
            return ConnectionResult(success=False, errors=[f"marketplace add failed: {msg}"])

        proc = subprocess.run(
            ["claude", "plugin", "install", _PLUGIN_ID, "--scope", "user"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if proc.returncode != 0:
            msg = proc.stderr.decode(errors="replace").strip()
            return ConnectionResult(success=False, errors=[f"plugin install failed: {msg}"])

        self._cleanup_legacy()

        return ConnectionResult(
            success=True,
            mcp_entry={"scope": "plugin", "plugin_name": _PLUGIN_ID},
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            return True

        subprocess.run(
            ["claude", "plugin", "uninstall", _PLUGIN_ID, "--scope", "user", "-y"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        return True

    @staticmethod
    def _cleanup_legacy() -> None:
        root = agent_config_root(AgentName.CLAUDE)

        skill_path = root / "skills" / "agentnet" / "SKILL.md"
        if skill_path.exists():
            skill_path.unlink()
            skill_dir = skill_path.parent
            if skill_dir.exists() and not any(skill_dir.iterdir()):
                skill_dir.rmdir()

        claude_json = root.parent / ".claude.json"
        if claude_json.exists():
            try:
                data = json.loads(claude_json.read_text())
                if "agentnet" in data.get("mcpServers", {}):
                    data["mcpServers"].pop("agentnet")
                    claude_json.write_text(json.dumps(data, indent=2) + "\n")
            except (json.JSONDecodeError, OSError):
                pass

        settings_path = root / "settings.json"
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text())
                allow = data.get("permissions", {}).get("allow", [])
                if "mcp__agentnet__*" in allow:
                    allow.remove("mcp__agentnet__*")
                    settings_path.write_text(json.dumps(data, indent=2) + "\n")
            except (json.JSONDecodeError, OSError):
                pass
