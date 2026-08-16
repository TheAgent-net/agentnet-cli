"""Install the AgentNet skill-fire hooks into Cursor's ``~/.cursor/hooks.json``.

Registers three hooks that mirror the Claude flow: ``beforeSubmitPrompt`` (spawn the background
discovery worker), ``preToolUse`` (hard-nudge — deny the first tool call once and feed the skill
to the agent), and ``stop`` (followup fallback for no-tool answers).

Cursor's schema is ``{"version": 1, "hooks": {<event>: [{"command", "type"}]}}`` — flatter than
Claude's ``settings.json`` (no per-block matcher nesting; the ``preToolUse`` deny-once is enforced
in the hook code, not by a matcher). Install is idempotent and preserves any existing hooks.
"""

from __future__ import annotations

import json
from typing import Any

from ..infra.paths import AgentName, agent_config_root

# event -> command. Deny-once/tool selection is handled in cursor-hook, so no matcher is needed.
_HOOKS: dict[str, str] = {
    "beforeSubmitPrompt": "agentnet cursor-hook --pre",
    "preToolUse": "agentnet cursor-hook --peek",
    "stop": "agentnet cursor-hook --post",
}


def _hooks_path():
    return agent_config_root(AgentName.CURSOR) / "hooks.json"


def _load(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_agentnet_cmd(cmd: Any) -> bool:
    from ..infra.proc import is_agentnet_subcommand  # noqa: PLC0415

    return is_agentnet_subcommand(cmd, "cursor-hook")


def _event_has_agentnet(entries: list[Any]) -> bool:
    return any(isinstance(e, dict) and _is_agentnet_cmd(e.get("command")) for e in entries)


def install() -> tuple[bool, str]:
    """Add the AgentNet hooks to ~/.cursor/hooks.json. Returns (changed, path)."""
    path = _hooks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    changed = False
    for event, command in _HOOKS.items():
        entries = hooks.get(event)
        if not isinstance(entries, list):
            entries = []
            hooks[event] = entries
        if not _event_has_agentnet(entries):
            entries.append({"command": command, "type": "command"})
            changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n")
    return changed, str(path)


def uninstall() -> tuple[bool, str]:
    """Remove the AgentNet hooks from ~/.cursor/hooks.json. Returns (changed, path)."""
    path = _hooks_path()
    data = _load(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False, str(path)

    changed = False
    for event in list(_HOOKS):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        kept = [
            e for e in entries if not (isinstance(e, dict) and _is_agentnet_cmd(e.get("command")))
        ]
        if len(kept) != len(entries):
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
