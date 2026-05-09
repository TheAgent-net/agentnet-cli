from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from ..paths import AgentName, agent_config_root, agentnet_home
from .base import AgentConnector, ConnectionResult, DetectionResult
from .shims import load_shim


def _vscode_user_dirs() -> list[Path]:
    system = platform.system()
    home = Path.home()
    candidates: list[Path] = []

    if system == "Darwin":
        base = home / "Library" / "Application Support"
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(base / variant / "User")
    elif system == "Linux":
        config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(config / variant / "User")
    elif system == "Windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        for variant in ["Code", "Code - Insiders"]:
            candidates.append(appdata / variant / "User")

    return [p for p in candidates if p.exists()]


class VSCodeConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        dot_vscode = agent_config_root(AgentName.VSCODE)
        has_extensions = dot_vscode.exists() and (dot_vscode / "extensions").exists()
        user_dirs = _vscode_user_dirs()
        if has_extensions or user_dirs:
            config_root = user_dirs[0] if user_dirs else dot_vscode
            return DetectionResult(
                agent_name=AgentName.VSCODE,
                detected=True,
                config_root=config_root,
            )
        return DetectionResult(agent_name=AgentName.VSCODE, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        files_created: list[Path] = []
        files_modified: list[tuple[Path, Path]] = []
        mcp_entry_info: dict[str, Any] = {}
        mcp_config = self._build_mcp_entry()

        vscode_files: list[str] = []
        for user_dir in _vscode_user_dirs():
            mcp_path = user_dir / "mcp.json"
            backup = agentnet_home() / "backups" / "vscode" / mcp_path.parent.parent.name / "mcp.json.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            if mcp_path.exists():
                backup.write_bytes(mcp_path.read_bytes())
                files_modified.append((mcp_path, backup))
            self._merge_mcp(mcp_path, mcp_config)
            vscode_files.append(str(mcp_path))

        mcp_entry_info["vscode_files"] = vscode_files

        user_dirs = _vscode_user_dirs()
        instructions_dir = user_dirs[0] if user_dirs else agent_config_root(AgentName.VSCODE)
        instructions_path = instructions_dir / ".github" / "copilot-instructions.md"
        instructions_path.parent.mkdir(parents=True, exist_ok=True)
        instructions_path.write_text(load_shim("vscode/instructions.md"))
        files_created.append(instructions_path)

        return ConnectionResult(
            success=True,
            files_created=files_created,
            files_modified=files_modified,
            mcp_entry=mcp_entry_info,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        for path_str in connection_manifest.get("files_created", []):
            p = Path(path_str)
            if p.exists():
                p.unlink()

        mcp_info = connection_manifest.get("mcp_registered", {})
        for vsc_path_str in mcp_info.get("vscode_files", []):
            vsc_path = Path(vsc_path_str)
            if vsc_path.exists():
                data = json.loads(vsc_path.read_text())
                data.get("servers", {}).pop("agentnet", None)
                vsc_path.write_text(json.dumps(data, indent=2) + "\n")
        return True

    def _build_mcp_entry(self) -> dict[str, Any]:
        agentnet_bin = shutil.which("agentnet")
        if agentnet_bin:
            return {
                "type": "stdio",
                "command": agentnet_bin,
                "args": ["mcp-serve"],
            }
        return {
            "type": "stdio",
            "command": "uvx",
            "args": ["agentnet-cli", "mcp-serve"],
        }

    def _merge_mcp(self, mcp_path: Path, entry: dict[str, Any]) -> None:
        data: dict[str, Any] = {}
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
        data.setdefault("servers", {})
        data["servers"]["agentnet"] = entry
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(json.dumps(data, indent=2) + "\n")
