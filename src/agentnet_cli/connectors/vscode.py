"""VS Code connector for user MCP config and Copilot instructions."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

from ..infra.paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


def _vscode_user_dirs(*, home: Path | None = None, windows_layout: bool = False) -> list[Path]:
    system = platform.system()
    root = home if home is not None else Path.home()
    candidates: list[Path] = []

    if windows_layout or (home is None and system == "Windows"):
        if home is not None:
            appdata = root / "AppData" / "Roaming"
        else:
            appdata = Path(os.environ.get("APPDATA", root / "AppData" / "Roaming"))
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(appdata / variant / "User")
    elif home is None and system == "Darwin":
        base = root / "Library" / "Application Support"
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(base / variant / "User")
    elif home is not None and (root / "Library" / "Application Support").exists():
        base = root / "Library" / "Application Support"
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(base / variant / "User")
    else:
        if home is None:
            config = Path(os.environ.get("XDG_CONFIG_HOME", root / ".config"))
        else:
            config = root / ".config"
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(config / variant / "User")

    return [p for p in candidates if p.exists()]


class VSCodeConnector(AgentConnector):
    """Connect VS Code through user MCP files and Copilot instructions."""

    def _user_dirs(self) -> list[Path]:
        if self.env.kind == "local":
            return _vscode_user_dirs()
        return _vscode_user_dirs(
            home=self.env.home,
            windows_layout=self.env.kind == "windows",
        )

    def detect(self) -> DetectionResult:
        """Detect VS Code or Copilot config in this environment."""
        dot_vscode = agent_config_root(AgentName.VSCODE, self.env)
        has_extensions = dot_vscode.exists() and (dot_vscode / "extensions").exists()
        user_dirs = self._user_dirs()
        if has_extensions or user_dirs:
            config_root = user_dirs[0] if user_dirs else dot_vscode
            return DetectionResult(
                agent_name=AgentName.VSCODE,
                detected=True,
                config_root=config_root,
                env_key=self.env.key,
                env_label=self.env.label,
            )
        return DetectionResult(
            agent_name=AgentName.VSCODE,
            detected=False,
            env_key=self.env.key,
            env_label=self.env.label,
        )

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Write user MCP config and Copilot instructions for VS Code."""
        files_created: list[Path] = []
        files_modified: list[tuple[Path, Path]] = []
        mcp_entry_info: dict[str, Any] = {}
        mcp_config = self._build_mcp_entry()

        vscode_files: list[str] = []
        user_dirs = self._user_dirs()
        for user_dir in user_dirs:
            mcp_path = user_dir / "mcp.json"
            backup = (
                agentnet_home() / "backups" / "vscode" / mcp_path.parent.parent.name / "mcp.json.bak"
            )
            backup.parent.mkdir(parents=True, exist_ok=True)
            if mcp_path.exists():
                backup.write_bytes(mcp_path.read_bytes())
                files_modified.append((mcp_path, backup))
            self._merge_mcp(mcp_path, mcp_config)
            vscode_files.append(str(mcp_path))

        mcp_entry_info["vscode_files"] = vscode_files

        instructions_dir = user_dirs[0] if user_dirs else agent_config_root(AgentName.VSCODE, self.env)
        instructions_path = instructions_dir / ".github" / "copilot-instructions.md"
        instructions_path.parent.mkdir(parents=True, exist_ok=True)
        instructions_path.write_text(load_shim("vscode/instructions.md"), encoding="utf-8")
        files_created.append(instructions_path)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            files_modified=files_modified,
            mcp_entry=mcp_entry_info,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Remove created files and the AgentNet MCP entry from VS Code config."""
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()

        mcp_info = connection_manifest.get("mcp_registered", {})
        for vsc_path_str in mcp_info.get("vscode_files", []):
            vsc_path = Path(vsc_path_str)
            if vsc_path.exists():
                data = _load_json_object(vsc_path)
                data.get("servers", {}).pop("agentnet", None)
                vsc_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True

    def _build_mcp_entry(self) -> dict[str, Any]:
        from .mcp_entry import make_mcp_server_entry

        entry = make_mcp_server_entry(self.env)
        entry["type"] = "stdio"
        return entry

    def _merge_mcp(self, mcp_path: Path, entry: dict[str, Any]) -> None:
        from ..infra.config import write_file_safe

        # Empty or invalid mcp.json is common on fresh VS Code installs — start fresh.
        data = _load_json_object(mcp_path) if mcp_path.exists() else {}
        data.setdefault("servers", {})
        data["servers"]["agentnet"] = entry
        write_file_safe(mcp_path, json.dumps(data, indent=2) + "\n")


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from *path*. Empty or invalid files become ``{}``."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
