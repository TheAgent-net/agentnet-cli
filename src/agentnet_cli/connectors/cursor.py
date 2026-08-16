"""Cursor connector for MCP, rules, subagents, permissions, hooks, and plugin."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..infra.package_paths import bundled_cursor_plugin
from ..infra.paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim

_PLUGIN_NAME = "agentnet"


def _plugin_source() -> Path:
    plugin = bundled_cursor_plugin()
    manifest = plugin / ".cursor-plugin" / "plugin.json"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Bundled Cursor integration missing at {plugin}. "
            "Reinstall agentnet-cli: pip install --upgrade agentnet-cli"
        )
    return plugin


class CursorConnector(AgentConnector):
    """Connect Cursor through MCP config, rules, subagents, permissions, hooks, and plugin."""

    def detect(self) -> DetectionResult:
        """Detect Cursor config in this environment."""
        root = agent_config_root(AgentName.CURSOR, self.env)
        base = DetectionResult(
            agent_name=AgentName.CURSOR,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )
        if not root.exists():
            return base
        for vf in ["extensions", "mcp.json", "cli-config.json"]:
            if (root / vf).exists():
                return DetectionResult(
                    agent_name=AgentName.CURSOR,
                    detected=True,
                    config_root=root,
                    env_key=self.env.key,
                    env_label=self.env.label,
                )
        return base

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Write MCP, rules, subagents, permissions, skill-fire hooks, and local plugin."""
        files_created: list[Path] = []
        root = agent_config_root(AgentName.CURSOR, self.env)

        # Layer 1: MCP
        mcp_path = root / "mcp.json"
        mcp_entry = self._write_mcp(mcp_path)

        # Layer 2a: Rule (user-level fallback when local plugins are disabled)
        rules_dir = root / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        mdc_path = rules_dir / "agentnet.mdc"
        mdc_path.write_text(load_shim("cursor/agentnet.mdc"), encoding="utf-8")
        files_created.append(mdc_path)

        # Layer 2b: Subagent
        agents_dir = root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "agentnet.md"
        agent_path.write_text(load_shim("cursor/agent.md"), encoding="utf-8")
        files_created.append(agent_path)

        # Layer 3: MCP auto-approve
        perms_path = self._write_permissions(root)
        files_created.append(perms_path)

        # Layer 4: every-prompt skill-fire hooks (~/.cursor/hooks.json)
        from .cursor_hook import install as install_hooks

        install_hooks(self.env)

        # Layer 5: native Cursor plugin (~/.cursor/plugins/local/agentnet)
        plugin_dir = self._install_plugin(root)
        mcp_entry["plugin_dir"] = str(plugin_dir)

        return ConnectionResult(
            success=True, files_created=files_created, mcp_entry=mcp_entry,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Remove plugin, hooks, created files, and the AgentNet MCP entry."""
        from .cursor_hook import uninstall as uninstall_hooks

        uninstall_hooks(self.env)

        mcp_info = connection_manifest.get("mcp_registered", {})
        plugin_dir_str = mcp_info.get("plugin_dir")
        plugin_dir = (
            Path(plugin_dir_str)
            if plugin_dir_str
            else agent_config_root(AgentName.CURSOR, self.env)
            / "plugins"
            / "local"
            / _PLUGIN_NAME
        )
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        deleted: list[Path] = []
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.name == "permissions.json":
                self._remove_permissions_entry(p)
                continue
            if p.exists():
                p.unlink()
                deleted.append(p)

        for p in deleted:
            if p.parent.exists() and not any(p.parent.iterdir()):
                p.parent.rmdir()

        mcp_file = mcp_info.get("file")
        if mcp_file:
            mcp_path = Path(mcp_file)
            if mcp_path.exists():
                data = json.loads(mcp_path.read_text(encoding="utf-8"))
                data.get("mcpServers", {}).pop("agentnet", None)
                mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True

    def _install_plugin(self, root: Path) -> Path:
        """Copy the bundled Cursor plugin into ~/.cursor/plugins/local/agentnet."""
        plugin_dir = root / "plugins" / "local" / _PLUGIN_NAME
        source = _plugin_source()
        plugin_dir.parent.mkdir(parents=True, exist_ok=True)
        if plugin_dir.exists() or plugin_dir.is_symlink():
            shutil.rmtree(plugin_dir)
        shutil.copytree(source, plugin_dir)
        return plugin_dir

    def _write_mcp(self, mcp_path: Path) -> dict[str, Any]:
        from ..infra.config import write_file_safe
        from .mcp_entry import make_mcp_server_entry

        data: dict[str, Any] = {}
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        data.setdefault("mcpServers", {})
        data["mcpServers"]["agentnet"] = make_mcp_server_entry(
            self.env,
            env_vars={"AGENTNET_TOKEN": "${env:AGENTNET_TOKEN}"},
        )
        write_file_safe(mcp_path, json.dumps(data, indent=2) + "\n")
        return {"scope": "global", "file": str(mcp_path), "server_name": "agentnet"}

    def _write_permissions(self, root: Path) -> Path:
        perms_path = root / "permissions.json"
        data: dict[str, Any] = {}
        if perms_path.exists():
            data = json.loads(perms_path.read_text(encoding="utf-8"))
        allowlist = set(data.get("mcpAllowlist", []))
        allowlist.add("agentnet:*")
        data["mcpAllowlist"] = sorted(allowlist)
        perms_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return perms_path

    @staticmethod
    def _remove_permissions_entry(perms_path: Path) -> None:
        if not perms_path.exists():
            return
        data = json.loads(perms_path.read_text(encoding="utf-8"))
        allowlist = [entry for entry in data.get("mcpAllowlist", []) if entry != "agentnet:*"]
        if allowlist:
            data["mcpAllowlist"] = allowlist
            perms_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            data.pop("mcpAllowlist", None)
            if data:
                perms_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            else:
                perms_path.unlink()
