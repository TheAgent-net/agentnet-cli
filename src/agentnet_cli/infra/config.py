"""Read and write local config in ``~/.agentnet/config.json``."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .paths import agentnet_home


def write_file_safe(path: Path, content: str, *, restricted: bool = False) -> None:
    """Write a full file, then replace the target path.

    Use this for config and hook JSON. Do not leave a half-written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        if restricted and os.name != "nt":
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _config_path() -> Path:
    """Return the path to ``config.json``."""
    return agentnet_home() / "config.json"


def load_config() -> dict[str, Any] | None:
    """Load local config. Return ``None`` when the file is missing or bad."""
    path = _config_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Warning: {path} is corrupted, ignoring", file=sys.stderr)
        return None


def save_config(data: dict[str, Any]) -> None:
    """Write local config to disk."""
    path = _config_path()
    write_file_safe(path, json.dumps(data, indent=2) + "\n", restricted=True)


def load_agent_paths() -> dict[str, str]:
    """Return custom agent binary paths from config."""
    config = load_config()
    if not config:
        return {}
    return config.get("agent_paths", {})


def save_agent_path(agent_name: str, binary_path: str) -> None:
    """Save a custom agent binary path in config."""
    config = load_config() or {}
    paths = config.setdefault("agent_paths", {})
    paths[agent_name] = binary_path
    save_config(config)


def remove_agent_path(agent_name: str) -> bool:
    """Remove a custom agent binary path. Return True when it existed."""
    config = load_config() or {}
    paths = config.get("agent_paths", {})
    if agent_name not in paths:
        return False
    del paths[agent_name]
    save_config(config)
    return True
