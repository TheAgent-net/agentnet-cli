"""Paths for agentnet home, agent config roots, and agent binaries."""

from __future__ import annotations

import os
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .environments import Environment


class AgentName(str, Enum):
    """Known agent harness names.

    Uses ``(str, Enum)`` rather than ``enum.StrEnum`` so the CLI stays
    importable on Python 3.10 (``StrEnum`` is 3.11+).
    """

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
    """Return ``~/.agentnet``."""
    return Path.home() / ".agentnet"


def agent_config_root(agent: AgentName, env: Environment | None = None) -> Path:
    """Return the config root for *agent* in *env* (default: local home)."""
    if env is None:
        from .environments import local_environment  # noqa: PLC0415

        env = local_environment()

    if agent == AgentName.CLAUDE:
        if env.kind == "local" and sys.platform == "win32":
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                return Path(appdata) / "Claude"
        if env.kind == "windows":
            return env.home / "AppData" / "Roaming" / "Claude"

    return env.home / _AGENT_DOT_DIRS[agent]


def agent_binary_name(agent: AgentName) -> str:
    """Return the default binary name for *agent*."""
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
    """Return the display name for *agent*."""
    return _DISPLAY_NAMES[agent]


def short_path(p: Path | str | None) -> str:
    """Return a path with the home directory replaced by ``~``."""
    if p is None:
        return "—"
    s = str(p)
    home = str(Path.home())
    if sys.platform == "win32":
        if os.path.normcase(s).startswith(os.path.normcase(home)):
            return "~" + s[len(home):]
        return s
    if s.startswith(home):
        return "~" + s[len(home):]
    return s


def find_agent_binary(agent: AgentName, custom_paths: dict[str, str] | None = None) -> Path | None:
    """Find the *agent* binary on PATH or in custom paths."""
    if custom_paths and agent.value in custom_paths:
        custom = Path(custom_paths[agent.value])
        if custom.is_file():
            return custom
    for bin_name in _AGENT_BINARIES[agent]:
        found = shutil.which(bin_name)
        if found:
            return Path(found)
    return None
