"""Install the AgentNet every-prompt hooks directly into Claude Code's settings.json.

Registers three hooks: ``UserPromptSubmit`` (spawn a background discovery worker),
``PostToolUse`` (steer the agent mid-flight once the outcome is ready), and ``Stop``
(guaranteed fallback that folds the outcome in). Same effect as the bundled plugin, but
written straight into ``~/.claude/settings.json`` so it works in one command regardless of
Claude Code version.

``PostToolUse`` is tool-scoped so its block carries a ``*`` matcher (all tools);
``UserPromptSubmit`` and ``Stop`` are not tool-scoped, so their blocks carry no matcher.
"""

from __future__ import annotations

import json
from typing import Any

from ..infra.paths import AgentName, agent_config_root

# event -> (command, matcher). matcher=None for non-tool-scoped events.
_HOOKS: dict[str, tuple[str, str | None]] = {
    "UserPromptSubmit": ("agentnet skill-hook --pre", None),
    "PostToolUse": ("agentnet skill-hook --peek", "*"),
    "Stop": ("agentnet skill-hook --post", None),
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
    return isinstance(cmd, str) and cmd.startswith("agentnet skill-hook")


def _block(command: str, matcher: str | None) -> dict[str, Any]:
    block: dict[str, Any] = {}
    if matcher is not None:
        block["matcher"] = matcher
    block["hooks"] = [{"type": "command", "command": command}]
    return block


def _event_has_agentnet(blocks: list[Any]) -> bool:
    for b in blocks:
        if isinstance(b, dict) and any(
            isinstance(h, dict) and _is_agentnet_cmd(h.get("command")) for h in b.get("hooks", [])
        ):
            return True
    return False


def install() -> tuple[bool, str]:
    """Add the UserPromptSubmit/Stop hooks to settings.json. Returns (changed, path)."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    changed = False
    for event, (command, matcher) in _HOOKS.items():
        blocks = hooks.get(event)
        if not isinstance(blocks, list):
            blocks = []
            hooks[event] = blocks
        if not _event_has_agentnet(blocks):
            blocks.append(_block(command, matcher))
            changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n")
    return changed, str(path)


def uninstall() -> tuple[bool, str]:
    """Remove the AgentNet every-prompt hooks from settings.json. Returns (changed, path)."""
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
