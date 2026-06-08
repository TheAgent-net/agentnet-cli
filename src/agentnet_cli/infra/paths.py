from __future__ import annotations

import os
import shutil
import sys
from enum import StrEnum
from pathlib import Path


class AgentName(StrEnum):
    CLAUDE = "claude"
    CURSOR = "cursor"
    COPILOT = "copilot"
    VSCODE = "vscode"
    CODEX = "codex"
    HERMES = "hermes"
    OPENCLAW = "openclaw"


_AGENT_DOT_DIRS: dict[AgentName, str] = {
    AgentName.CLAUDE: ".claude",
    AgentName.CURSOR: ".cursor",
    AgentName.COPILOT: ".copilot",
    AgentName.VSCODE: ".vscode",
    AgentName.CODEX: ".codex",
    AgentName.HERMES: ".hermes",
    AgentName.OPENCLAW: ".openclaw",
}

_AGENT_BINARIES: dict[AgentName, list[str]] = {
    AgentName.CLAUDE: ["claude"],
    AgentName.CURSOR: ["cursor"],
    AgentName.COPILOT: ["copilot"],
    AgentName.VSCODE: ["code"],
    AgentName.CODEX: ["codex"],
    AgentName.HERMES: ["hermes"],
    AgentName.OPENCLAW: ["openclaw"],
}


def agentnet_home() -> Path:
    return Path.home() / ".agentnet"


def agent_config_root(agent: AgentName) -> Path:
    if agent == AgentName.CLAUDE and sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Claude"
    return Path.home() / _AGENT_DOT_DIRS[agent]


def agent_binary_name(agent: AgentName) -> str:
    return _AGENT_BINARIES[agent][0]


_DISPLAY_NAMES: dict[AgentName, str] = {
    AgentName.CLAUDE: "Claude",
    AgentName.CURSOR: "Cursor",
    AgentName.COPILOT: "GitHub Copilot",
    AgentName.VSCODE: "VS Code",
    AgentName.CODEX: "Codex",
    AgentName.HERMES: "Hermes",
    AgentName.OPENCLAW: "OpenClaw",
}


def agent_display_name(agent: AgentName) -> str:
    return _DISPLAY_NAMES[agent]


def short_path(p: Path | str | None) -> str:
    if p is None:
        return "—"
    s = str(p)
    home = str(Path.home())
    if s.startswith(home):
        return "~" + s[len(home):]
    return s


def find_agent_binary(agent: AgentName, custom_paths: dict[str, str] | None = None) -> Path | None:
    if custom_paths and agent.value in custom_paths:
        custom = Path(custom_paths[agent.value])
        if custom.is_file():
            return custom
    for bin_name in _AGENT_BINARIES[agent]:
        found = shutil.which(bin_name)
        if found:
            return Path(found)
    return None
