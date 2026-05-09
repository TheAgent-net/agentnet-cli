from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from ..paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult

_PLUGIN_NAME = "agentnet"


def _hermes_plugin_source() -> Path:
    from ..hermes_plugin import _PLUGIN_DIR  # noqa: PLC0415

    return _PLUGIN_DIR


class HermesConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.HERMES)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.HERMES, detected=False)
        if (root / "config.yaml").exists():
            return DetectionResult(
                agent_name=AgentName.HERMES,
                detected=True,
                config_root=root,
            )
        return DetectionResult(agent_name=AgentName.HERMES, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        root = agent_config_root(AgentName.HERMES)
        config_path = root / "config.yaml"
        plugin_dir = root / "plugins" / _PLUGIN_NAME

        source = _hermes_plugin_source()
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        shutil.copytree(source, plugin_dir)

        for cache_dir in plugin_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir)

        files_created = [f for f in plugin_dir.rglob("*") if f.is_file()]

        data: dict[str, Any] = {}
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}

        plugins = data.setdefault("plugins", {})
        enabled = plugins.setdefault("enabled", [])
        if _PLUGIN_NAME not in enabled:
            enabled.append(_PLUGIN_NAME)

        self._cleanup_legacy(data, root)

        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

        return ConnectionResult(
            success=True,
            files_created=files_created,
            mcp_entry={
                "scope": "plugin",
                "plugin_dir": str(plugin_dir),
            },
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        root = agent_config_root(AgentName.HERMES)
        config_path = root / "config.yaml"

        mcp_info = connection_manifest.get("mcp_registered", {})
        plugin_dir_str = mcp_info.get("plugin_dir")
        if plugin_dir_str:
            plugin_dir = Path(plugin_dir_str)
        else:
            plugin_dir = root / "plugins" / _PLUGIN_NAME

        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}
            plugins = data.get("plugins", {})
            if isinstance(plugins, dict):
                enabled = plugins.get("enabled", [])
                if isinstance(enabled, list) and _PLUGIN_NAME in enabled:
                    enabled.remove(_PLUGIN_NAME)
            self._cleanup_legacy(data, root)
            config_path.write_text(
                yaml.dump(data, default_flow_style=False, sort_keys=False)
            )

        return True

    @staticmethod
    def _cleanup_legacy(data: dict[str, Any], root: Path) -> None:
        mcp_servers = data.get("mcp_servers", {})
        if isinstance(mcp_servers, dict):
            mcp_servers.pop("agentnet", None)

        old_mcp = data.get("mcp", {})
        if isinstance(old_mcp, dict):
            old_servers = old_mcp.get("servers", {})
            if isinstance(old_servers, dict):
                old_servers.pop("agentnet", None)

        platform_toolsets = data.get("platform_toolsets", {})
        if isinstance(platform_toolsets, dict):
            for toolsets in platform_toolsets.values():
                if isinstance(toolsets, list) and "mcp-agentnet" in toolsets:
                    toolsets.remove("mcp-agentnet")

        top_toolsets = data.get("toolsets")
        if isinstance(top_toolsets, list) and "mcp-agentnet" in top_toolsets:
            top_toolsets.remove("mcp-agentnet")

        old_skill_dir = root / "skills" / "agentnet"
        if old_skill_dir.exists():
            shutil.rmtree(old_skill_dir)
