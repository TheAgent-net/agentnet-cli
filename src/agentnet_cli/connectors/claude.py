from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from ..infra.package_paths import bundled_claude_marketplace
from ..infra.paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult

_PLUGIN_ID = "agentnet@agentnet-cli"
_SUBPROCESS_TIMEOUT = 120


def _marketplace_source() -> str:
    marketplace = bundled_claude_marketplace()
    manifest = marketplace / ".claude-plugin" / "marketplace.json"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Bundled Claude integration missing at {marketplace}. "
            "Reinstall agentnet-cli: pip install --upgrade agentnet-cli"
        )
    return str(marketplace)


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

        # 1. Install the AgentNet every-prompt hook straight into settings.json.
        #    This is the reliable path: every prompt fires AgentNet (discover +
        #    fold in relevant skills). It does NOT depend on the plugin marketplace
        #    flow (which errors on some Claude Code versions), so connect succeeds
        #    even if that fails.
        from .claude_search_hook import SettingsHookError
        from .claude_search_hook import install as install_search_hook

        errors: list[str] = []
        try:
            install_search_hook()
        except SettingsHookError as exc:
            # A malformed settings.json must not be overwritten; report and preserve it, but let
            # the rest of connect (MCP + plugin) still run.
            errors.append(str(exc))

        # 2. Best-effort: install the plugin for the discovery MCP tools and
        #    session hooks. `marketplace add` takes only <source> (no --scope).
        #    Failures here are non-fatal — the prompt hook above is already live.
        try:
            marketplace_src = _marketplace_source()
            proc = subprocess.run(
                ["claude", "plugin", "marketplace", "add", marketplace_src],
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            if proc.returncode == 0:
                proc = subprocess.run(
                    ["claude", "plugin", "install", _PLUGIN_ID, "--scope", "user"],
                    capture_output=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
                if proc.returncode != 0:
                    errors.append(
                        "plugin install (discovery tools) failed: "
                        + proc.stderr.decode(errors="replace").strip()
                    )
            else:
                errors.append(
                    "plugin marketplace add (discovery tools) failed: "
                    + proc.stderr.decode(errors="replace").strip()
                )
        except Exception as exc:  # noqa: BLE001 — plugin step is best-effort
            errors.append(f"plugin step skipped: {exc}")

        self._cleanup_legacy()

        return ConnectionResult(
            success=True,
            mcp_entry={"scope": "settings-hook", "search_fire": True},
            errors=errors,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        from .claude_search_hook import uninstall as uninstall_search_hook

        uninstall_search_hook()

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
