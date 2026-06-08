from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .paths import agentnet_home


def _atomic_write(path: Path, content: str, *, restricted: bool = False) -> None:
    """Write content atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content)
        if restricted and os.name != "nt":
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _config_path() -> Path:
    return agentnet_home() / "config.json"


def load_config() -> dict[str, Any] | None:
    path = _config_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"Warning: {path} is corrupted, ignoring", file=sys.stderr)
        return None


def save_config(data: dict[str, Any]) -> None:
    path = _config_path()
    _atomic_write(path, json.dumps(data, indent=2) + "\n", restricted=True)


def load_agent_paths() -> dict[str, str]:
    config = load_config()
    if not config:
        return {}
    return config.get("agent_paths", {})


def save_agent_path(agent_name: str, binary_path: str) -> None:
    config = load_config() or {}
    paths = config.setdefault("agent_paths", {})
    paths[agent_name] = binary_path
    save_config(config)


def remove_agent_path(agent_name: str) -> bool:
    config = load_config() or {}
    paths = config.get("agent_paths", {})
    if agent_name not in paths:
        return False
    del paths[agent_name]
    save_config(config)
    return True
