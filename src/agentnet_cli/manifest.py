from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import _atomic_write
from .paths import agentnet_home


def _manifest_path() -> Path:
    return agentnet_home() / "manifest.json"


def load_manifest() -> dict[str, Any]:
    path = _manifest_path()
    if not path.exists():
        return {"connections": {}}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"Warning: {path} is corrupted, ignoring", file=sys.stderr)
        return {"connections": {}}


def save_manifest(data: dict[str, Any]) -> None:
    path = _manifest_path()
    _atomic_write(path, json.dumps(data, indent=2) + "\n", restricted=True)


def record_connection(
    agent_name: str,
    *,
    files_created: list[Path],
    files_modified: list[tuple[Path, Path]] | list[Any],
    mcp_entry: dict[str, Any],
) -> None:
    from . import __version__  # noqa: PLC0415

    m = load_manifest()
    m["connections"][agent_name] = {
        "connected_at": datetime.now(UTC).isoformat(),
        "cli_version": __version__,
        "files_created": [str(p) for p in files_created],
        "files_modified": [
            {"path": str(p), "backup": str(b)} for p, b in files_modified
        ] if files_modified and isinstance(files_modified[0], tuple) else [],
        "mcp_registered": mcp_entry,
    }
    save_manifest(m)


def remove_connection(agent_name: str) -> None:
    m = load_manifest()
    m["connections"].pop(agent_name, None)
    save_manifest(m)
