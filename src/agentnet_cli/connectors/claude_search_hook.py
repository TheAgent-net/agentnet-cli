"""Install the AgentNet search hook directly into Claude Code's settings.json.

The plugin path (``agentnet connect claude``) installs the same PostToolUse hook,
but it goes through ``claude plugin marketplace add`` which can fail on some Claude
Code versions. This writes the hook straight into ``~/.claude/settings.json`` so
it works in one command regardless.
"""

from __future__ import annotations

import json
from typing import Any

from ..infra.paths import AgentName, agent_config_root

_MATCHER = "WebSearch|WebFetch"
_COMMAND = "agentnet hook-slate"


def _settings_path():
    return agent_config_root(AgentName.CLAUDE) / "settings.json"


def _load(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _hook_block() -> dict[str, Any]:
    return {"matcher": _MATCHER, "hooks": [{"type": "command", "command": _COMMAND}]}


def _has_agentnet_hook(blocks: list[Any]) -> bool:
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if any(
            isinstance(h, dict) and h.get("command") == _COMMAND for h in b.get("hooks", [])
        ):
            return True
    return False


def install() -> tuple[bool, str]:
    """Add the PostToolUse search hook to settings.json. Returns (changed, path)."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    post = hooks.setdefault("PostToolUse", [])
    if not isinstance(post, list):
        post = []
        hooks["PostToolUse"] = post
    if _has_agentnet_hook(post):
        return False, str(path)
    post.append(_hook_block())
    path.write_text(json.dumps(data, indent=2) + "\n")
    return True, str(path)


def uninstall() -> tuple[bool, str]:
    """Remove the AgentNet search hook from settings.json. Returns (changed, path)."""
    path = _settings_path()
    data = _load(path)
    post = data.get("hooks", {}).get("PostToolUse")
    if not isinstance(post, list):
        return False, str(path)
    kept = [
        b
        for b in post
        if not (
            isinstance(b, dict)
            and any(
                isinstance(h, dict) and h.get("command") == _COMMAND for h in b.get("hooks", [])
            )
        )
    ]
    if len(kept) == len(post):
        return False, str(path)
    if kept:
        data["hooks"]["PostToolUse"] = kept
    else:
        data["hooks"].pop("PostToolUse", None)
        if not data["hooks"]:
            data.pop("hooks", None)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return True, str(path)
