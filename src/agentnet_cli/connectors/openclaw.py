"""OpenClaw connector for plugin install and MCP server registration."""

from __future__ import annotations

import json
from typing import Any

from ..infra.package_paths import bundled_openclaw_plugin
from ..infra.paths import AgentName, agent_config_root, agentnet_home
from ..infra.proc import find_executable, run_tool
from .base import AgentConnector, ConnectionResult, DetectionResult
from .mcp_entry import make_mcp_server_entry

_PLUGIN_ID = "agentnet"
_MCP_SERVER_NAME = "agentnet"
_SUBPROCESS_TIMEOUT = 120


def _mcp_server_config(env) -> str:
    return json.dumps(make_mcp_server_entry(env))


def _plugin_source() -> str:
    plugin_root = bundled_openclaw_plugin()
    manifest = plugin_root / "openclaw.plugin.json"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Bundled OpenClaw integration missing at {plugin_root}. "
            "Reinstall agentnet-cli: pip install --upgrade agentnet-cli"
        )
    return str(plugin_root)


class OpenClawConnector(AgentConnector):
    """Connect OpenClaw through plugin install and MCP server registration."""

    def detect(self) -> DetectionResult:
        """Detect OpenClaw config in this environment."""
        root = agent_config_root(AgentName.OPENCLAW, self.env)
        if not root.exists():
            return DetectionResult(
                agent_name=AgentName.OPENCLAW,
                detected=False,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        if (root / "openclaw.json").exists():
            return DetectionResult(
                agent_name=AgentName.OPENCLAW,
                detected=True,
                config_root=root,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        return DetectionResult(
            agent_name=AgentName.OPENCLAW,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Install the AgentNet plugin and register the MCP server."""
        # Plugin install subprocess is local-only; mirrored envs get file-level detect only.
        if self.env.kind != "local":
            return ConnectionResult(
                success=False,
                errors=[
                    f"OpenClaw plugin install skipped for {self.env.label} "
                    "(run connect on that side)"
                ],
            )

        if not find_executable("openclaw"):
            return ConnectionResult(
                success=False,
                errors=["OpenClaw not found. Install it from https://docs.openclaw.ai"],
            )

        plugin_source = _plugin_source()

        proc = run_tool(
            "openclaw",
            ["plugins", "install", plugin_source, "--force"],
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if proc is None or proc.returncode != 0:
            msg = (
                proc.stderr.decode(errors="replace").strip()
                if proc is not None
                else "openclaw not found"
            )
            return ConnectionResult(success=False, errors=[f"plugin install failed: {msg}"])

        proc = run_tool(
            "openclaw",
            ["mcp", "set", _MCP_SERVER_NAME, _mcp_server_config(self.env)],
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if proc is None or proc.returncode != 0:
            msg = (
                proc.stderr.decode(errors="replace").strip()
                if proc is not None
                else "openclaw not found"
            )
            return ConnectionResult(success=False, errors=[f"mcp set failed: {msg}"])

        self._cleanup_legacy()

        return ConnectionResult(
            success=True,
            mcp_entry={"scope": "plugin", "plugin_id": _PLUGIN_ID},
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Remove the MCP server and uninstall the AgentNet plugin."""
        if self.env.kind == "local":
            run_tool(
                "openclaw",
                ["mcp", "unset", _MCP_SERVER_NAME],
                timeout=_SUBPROCESS_TIMEOUT,
            )
            run_tool(
                "openclaw",
                ["plugins", "uninstall", _PLUGIN_ID, "--force"],
                timeout=_SUBPROCESS_TIMEOUT,
            )
        return True

    def _cleanup_legacy(self) -> None:
        root = agent_config_root(AgentName.OPENCLAW, self.env)

        config_path = root / "openclaw.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                if "agentnet-gateway" in data.get("plugins", {}):
                    data["plugins"].pop("agentnet-gateway")
                    config_path.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
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
