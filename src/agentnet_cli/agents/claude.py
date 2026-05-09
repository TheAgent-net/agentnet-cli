from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


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
        files_created: list[Path] = []
        files_modified: list[tuple[Path, Path]] = []

        root = agent_config_root(AgentName.CLAUDE)

        # Layer 1: MCP server registration in ~/.claude.json
        claude_json = root.parent / ".claude.json"
        if claude_json.exists():
            backup = agentnet_home() / "backups" / "claude" / "claude.json.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(claude_json.read_bytes())
            files_modified.append((claude_json, backup))
        mcp_entry = self._write_mcp(claude_json)

        # Layer 2: Skill injection
        skill_dir = root / "skills" / "agentnet"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(load_shim("claude/skill.md"))
        files_created.append(skill_path)

        # Layer 3: Permission auto-approval
        settings_path = root / "settings.json"
        if settings_path.exists():
            self._merge_permissions(settings_path)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            files_modified=files_modified,
            mcp_entry=mcp_entry,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()
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

    def _write_mcp(self, claude_json: Path) -> dict[str, Any]:
        import shutil  # noqa: PLC0415

        if claude_json.exists():
            data = json.loads(claude_json.read_text())
        else:
            data = {}
        data.setdefault("mcpServers", {})

        agentnet_bin = shutil.which("agentnet")
        if agentnet_bin:
            data["mcpServers"]["agentnet"] = {
                "command": agentnet_bin,
                "args": ["mcp-serve"],
            }
        else:
            data["mcpServers"]["agentnet"] = {
                "command": "uvx",
                "args": ["agentnet-cli", "mcp-serve"],
                "env": {"AGENTNET_TOKEN": "${AGENTNET_TOKEN}"},
            }
        claude_json.write_text(json.dumps(data, indent=2) + "\n")
        return {"scope": "user", "file": str(claude_json), "server_name": "agentnet"}

    def _merge_permissions(self, settings_path: Path) -> None:
        data = json.loads(settings_path.read_text())
        perms = data.setdefault("permissions", {})
        allow = perms.setdefault("allow", [])
        rule = "mcp__agentnet__*"
        if rule not in allow:
            allow.append(rule)
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
