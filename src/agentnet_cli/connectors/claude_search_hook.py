"""Install the AgentNet search hooks directly into Claude Code's settings.json.

Registers a PreToolUse hook (prefetch the AgentNet slate in the background) and a
PostToolUse hook (inject the prefetched slate) on ``WebSearch``. Same effect as the
bundled plugin, but written straight into ``~/.claude/settings.json`` so it works in
one command regardless of Claude Code version.
"""

from __future__ import annotations

import json
from typing import Any

from ..infra.paths import AgentName, agent_config_root

_MATCHER = "WebSearch"
_HOOKS: dict[str, str] = {
    "PreToolUse": "agentnet hook-slate --pre",
    "PostToolUse": "agentnet hook-slate --post",
}


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


def _is_agentnet_cmd(cmd: Any) -> bool:
    return isinstance(cmd, str) and cmd.startswith("agentnet hook-slate")


def _block(command: str) -> dict[str, Any]:
    return {"matcher": _MATCHER, "hooks": [{"type": "command", "command": command}]}


def _event_has_agentnet(blocks: list[Any]) -> bool:
    for b in blocks:
        if isinstance(b, dict) and any(
            isinstance(h, dict) and _is_agentnet_cmd(h.get("command")) for h in b.get("hooks", [])
        ):
            return True
    return False


def install() -> tuple[bool, str]:
    """Add the Pre/Post search hooks to settings.json. Returns (changed, path)."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    changed = False
    for event, command in _HOOKS.items():
        blocks = hooks.get(event)
        if not isinstance(blocks, list):
            blocks = []
            hooks[event] = blocks
        if not _event_has_agentnet(blocks):
            blocks.append(_block(command))
            changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n")
    return changed, str(path)


def uninstall() -> tuple[bool, str]:
    """Remove the AgentNet search hooks from settings.json. Returns (changed, path)."""
    path = _settings_path()
    data = _load(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False, str(path)

    changed = False
    for event in list(_HOOKS):
        blocks = hooks.get(event)
        if not isinstance(blocks, list):
            continue
        kept = [
            b
            for b in blocks
            if not (
                isinstance(b, dict)
                and any(
                    isinstance(h, dict) and _is_agentnet_cmd(h.get("command"))
                    for h in b.get("hooks", [])
                )
            )
        ]
        if len(kept) != len(blocks):
            changed = True
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)

    if changed:
        if not hooks:
            data.pop("hooks", None)
        path.write_text(json.dumps(data, indent=2) + "\n")
    return changed, str(path)
