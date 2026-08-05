from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from ..infra.paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult

_MCP_SERVER_NAME = "agentnet"


def _strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments from JSONC without touching them inside strings.

    opencode's config is ``opencode.jsonc``; the default ``$schema`` value is a URL containing
    ``//``, so a naive regex strip would corrupt it — this walks the text string-aware instead.
    Trailing commas (legal in JSONC) are also removed so ``json.loads`` accepts the result.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    stripped = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", stripped)  # drop trailing commas


def _load_config(path: Path) -> dict[str, Any] | None:
    """Parse an opencode config file. ``{}`` for missing/empty, ``None`` if unparseable (so we never
    clobber a config we can't understand)."""
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = json.loads(_strip_jsonc(text))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


class OpenCodeConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.OPENCODE)
        has_config = (root / "opencode.jsonc").exists() or (root / "opencode.json").exists()
        if has_config or shutil.which("opencode"):
            return DetectionResult(agent_name=AgentName.OPENCODE, detected=True, config_root=root)
        return DetectionResult(agent_name=AgentName.OPENCODE, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        files_created: list[Path] = []

        # Layer 1: the every-prompt skill-fire plugin (auto-loaded from ~/.config/opencode/plugins/).
        from .opencode_hook import install as install_plugin

        try:
            _changed, plugin_file = install_plugin()
        except FileNotFoundError as exc:
            return ConnectionResult(success=False, errors=[str(exc)])
        files_created.append(plugin_file)

        # Layer 2: the MCP server, in opencode.jsonc. Skipped (not fatal) if the config is present
        # but unparseable — the plugin, the core value, is already installed.
        mcp_entry = self._write_mcp()

        return ConnectionResult(
            success=True, files_created=files_created, mcp_entry=mcp_entry,
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        from .opencode_hook import uninstall as uninstall_plugin

        uninstall_plugin()

        mcp_info = connection_manifest.get("mcp_registered", {})
        mcp_file = mcp_info.get("file")
        if mcp_file:
            path = Path(mcp_file)
            data = _load_config(path)
            if data is not None and isinstance(data.get("mcp"), dict):
                data["mcp"].pop(_MCP_SERVER_NAME, None)
                if not data["mcp"]:
                    data.pop("mcp", None)
                path.write_text(json.dumps(data, indent=2) + "\n")
        return True

    def _config_path(self) -> Path:
        root = agent_config_root(AgentName.OPENCODE)
        jsonc = root / "opencode.jsonc"
        if jsonc.exists():
            return jsonc
        return root / "opencode.json"

    def _write_mcp(self) -> dict[str, Any]:
        config_path = self._config_path()
        data = _load_config(config_path)
        if data is None:
            return {}  # unparseable config — don't clobber it; MCP simply isn't registered

        mcp = data.setdefault("mcp", {})
        if not isinstance(mcp, dict):
            mcp = {}
            data["mcp"] = mcp

        agentnet_bin = shutil.which("agentnet")
        command = [agentnet_bin, "mcp-serve"] if agentnet_bin else ["uvx", "agentnet-cli", "mcp-serve"]
        # No `environment`: `agentnet mcp-serve` resolves credentials from ~/.agentnet/config.json,
        # and the subprocess inherits opencode's env (AGENTNET_TOKEN if the user set it there).
        mcp[_MCP_SERVER_NAME] = {"type": "local", "command": command, "enabled": True}

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")
        return {"scope": "global", "file": str(config_path), "server_name": _MCP_SERVER_NAME}
