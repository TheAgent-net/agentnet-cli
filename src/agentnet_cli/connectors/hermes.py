from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from ..infra.paths import AgentName, agent_config_root
from ..infra.proc import find_executable, run_tool
from .base import AgentConnector, ConnectionResult, DetectionResult

_PLUGIN_NAME = "agentnet"


def _hermes_plugin_source() -> Path:
    from ..infra.package_paths import bundled_hermes_plugin  # noqa: PLC0415

    return bundled_hermes_plugin()


def _find_hermes_venv(root: Path) -> Path | None:
    candidates = [
        root / "hermes-agent" / "venv",
        root / "venv",
    ]
    for venv in candidates:
        if (venv / "bin" / "python").exists() or (venv / "Scripts" / "python.exe").exists():
            return venv
    return None


def _install_into_hermes_venv(venv: Path) -> bool:
    python = venv / "bin" / "python"
    if not python.exists():
        python = venv / "Scripts" / "python.exe"
    if not python.exists():
        return False

    try:
        if find_executable("uv"):
            run_tool(
                "uv",
                ["pip", "install", "agentnet-cli", "--python", str(python)],
                timeout=120,
            )
        else:
            # python itself is already an absolute path — run directly.
            import subprocess  # noqa: PLC0415

            subprocess.run(  # noqa: S603
                [str(python), "-m", "pip", "install", "agentnet-cli"],
                capture_output=True,
                timeout=120,
            )
        return True
    except Exception:
        return False


class HermesConnector(AgentConnector):
    """Offer Hermes only where detect() succeeds.

    Skip cross-env Hermes in v1. The venv pip install and plugin copy need a local filesystem.
    """

    def detect(self) -> DetectionResult:
        # Skip cross-env Hermes entirely in v1 (venv + plugin install are local-fs only).
        if self.env.kind != "local":
            return DetectionResult(
                agent_name=AgentName.HERMES,
                detected=False,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        root = agent_config_root(AgentName.HERMES, self.env)
        if not root.exists():
            return DetectionResult(
                agent_name=AgentName.HERMES,
                detected=False,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        if (root / "config.yaml").exists():
            return DetectionResult(
                agent_name=AgentName.HERMES,
                detected=True,
                config_root=root,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        return DetectionResult(
            agent_name=AgentName.HERMES,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        root = agent_config_root(AgentName.HERMES, self.env)
        config_path = root / "config.yaml"
        plugin_dir = root / "plugins" / _PLUGIN_NAME

        hermes_venv = _find_hermes_venv(root)
        if hermes_venv:
            _install_into_hermes_venv(hermes_venv)

        source = _hermes_plugin_source()
        if plugin_dir.exists() or plugin_dir.is_symlink():
            shutil.rmtree(plugin_dir)
        shutil.copytree(source, plugin_dir, dirs_exist_ok=False)

        for cache_dir in plugin_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir)

        skill_src = source / "skills" / _PLUGIN_NAME
        skill_dst = root / "skills" / _PLUGIN_NAME
        if skill_src.is_dir():
            if skill_dst.exists():
                shutil.rmtree(skill_dst)
            shutil.copytree(skill_src, skill_dst)

        files_created = [f for f in plugin_dir.rglob("*") if f.is_file()]
        if skill_dst.exists():
            files_created.extend(f for f in skill_dst.rglob("*") if f.is_file())

        data: dict[str, Any] = {}
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        plugins = data.setdefault("plugins", {})
        enabled = plugins.setdefault("enabled", [])
        if _PLUGIN_NAME not in enabled:
            enabled.append(_PLUGIN_NAME)

        self._cleanup_legacy(data, root)

        config_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        from .hermes_hook import install as install_hooks

        install_hooks(self.env)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            mcp_entry={
                "scope": "plugin",
                "plugin_dir": str(plugin_dir),
            },
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        from .hermes_hook import uninstall as uninstall_hooks

        uninstall_hooks(self.env)

        root = agent_config_root(AgentName.HERMES, self.env)
        config_path = root / "config.yaml"

        mcp_info = connection_manifest.get("mcp_registered", {})
        plugin_dir_str = mcp_info.get("plugin_dir")
        if plugin_dir_str:
            plugin_dir = Path(plugin_dir_str)
        else:
            plugin_dir = root / "plugins" / _PLUGIN_NAME

        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        skill_dir = root / "skills" / _PLUGIN_NAME
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            plugins = data.get("plugins", {})
            if isinstance(plugins, dict):
                enabled = plugins.get("enabled", [])
                if isinstance(enabled, list) and _PLUGIN_NAME in enabled:
                    enabled.remove(_PLUGIN_NAME)
            self._cleanup_legacy(data, root)
            config_path.write_text(
                yaml.dump(data, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
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
