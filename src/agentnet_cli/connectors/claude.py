"""Claude Code connector for hooks, plugin marketplace, and legacy cleanup."""

from __future__ import annotations

import json
from typing import Any

from ..infra.package_paths import bundled_claude_marketplace
from ..infra.paths import AgentName, agent_config_root
from ..infra.proc import find_executable, run_tool
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
    """Connect Claude Code through settings hooks and the AgentNet plugin."""

    def detect(self) -> DetectionResult:
        """Detect Claude Code config in this environment."""
        root = agent_config_root(AgentName.CLAUDE, self.env)
        base = DetectionResult(
            agent_name=AgentName.CLAUDE,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )
        if not root.exists():
            return base
        for vf in ["settings.json"]:
            if (root / vf).exists():
                return DetectionResult(
                    agent_name=AgentName.CLAUDE,
                    detected=True,
                    config_root=root,
                    env_key=self.env.key,
                    env_label=self.env.label,
                )
        claude_json = root.parent / ".claude.json"
        if claude_json.exists():
            return DetectionResult(
                agent_name=AgentName.CLAUDE,
                detected=True,
                config_root=root,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        return base

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Install hooks and register the AgentNet Claude plugin."""
        from pathlib import Path

        from .claude_search_hook import SettingsHookError
        from .claude_search_hook import install as install_search_hook

        errors: list[str] = []

        # Local installs still require the claude binary (plugin + UX parity with prior CLI).
        if self.env.kind == "local" and not find_executable("claude"):
            return ConnectionResult(
                success=False,
                errors=["Claude Code not found. Install it from https://code.claude.com"],
            )

        # 1. Install the AgentNet every-prompt hook straight into settings.json.
        try:
            install_search_hook(self.env)
        except SettingsHookError as exc:
            errors.append(str(exc))

        # 2. Best-effort plugin marketplace — local env only (subprocess runs on this host).
        if self.env.kind == "local":
            try:
                marketplace_src = self.env.to_env_path(Path(_marketplace_source()))
                proc = run_tool(
                    "claude",
                    ["plugin", "marketplace", "add", marketplace_src],
                    timeout=_SUBPROCESS_TIMEOUT,
                )
                if proc is None:
                    errors.append("claude binary not found for plugin step")
                elif proc.returncode == 0:
                    proc = run_tool(
                        "claude",
                        ["plugin", "install", _PLUGIN_ID, "--scope", "user"],
                        timeout=_SUBPROCESS_TIMEOUT,
                    )
                    if proc is not None and proc.returncode != 0:
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
        else:
            errors.append(
                f"Claude plugin marketplace step skipped for {self.env.label} "
                "(run `claude plugin marketplace add` on that side if needed)"
            )

        self._cleanup_legacy()

        return ConnectionResult(
            success=True,
            mcp_entry={"scope": "settings-hook", "search_fire": True},
            errors=errors,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Remove hooks and uninstall the AgentNet Claude plugin."""
        from .claude_search_hook import uninstall as uninstall_search_hook

        uninstall_search_hook(self.env)

        if self.env.kind == "local":
            run_tool(
                "claude",
                ["plugin", "uninstall", _PLUGIN_ID, "--scope", "user", "-y"],
                timeout=_SUBPROCESS_TIMEOUT,
            )
        return True

    def _cleanup_legacy(self) -> None:
        root = agent_config_root(AgentName.CLAUDE, self.env)

        skill_path = root / "skills" / "agentnet" / "SKILL.md"
        if skill_path.exists():
            skill_path.unlink()
            skill_dir = skill_path.parent
            if skill_dir.exists() and not any(skill_dir.iterdir()):
                skill_dir.rmdir()

        claude_json = root.parent / ".claude.json"
        if claude_json.exists():
            try:
                data = json.loads(claude_json.read_text(encoding="utf-8"))
                if "agentnet" in data.get("mcpServers", {}):
                    data["mcpServers"].pop("agentnet")
                    claude_json.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
            except (json.JSONDecodeError, OSError):
                pass

        settings_path = root / "settings.json"
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
                allow = data.get("permissions", {}).get("allow", [])
                if "mcp__agentnet__*" in allow:
                    allow.remove("mcp__agentnet__*")
                    settings_path.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
            except (json.JSONDecodeError, OSError):
                pass
