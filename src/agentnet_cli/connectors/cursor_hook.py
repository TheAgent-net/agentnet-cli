"""Install AgentNet hooks in Cursor hooks.json.

This writes three hooks: ``beforeSubmitPrompt`` starts a discovery worker, ``preToolUse`` blocks
the first tool call once and sends the skill to the agent, and ``stop`` is the fallback. Cursor
uses ``{"version": 1, "hooks": {<event>: [{"command", "type"}]}}``. Install is idempotent and
keeps existing hooks.
"""

from __future__ import annotations

import json
from typing import Any

from ..infra.environments import Environment, local_environment
from ..infra.paths import AgentName, agent_config_root
from ..infra.proc import is_agentnet_subcommand

# event -> flag. Deny-once/tool selection is handled in cursor-hook, so no matcher is needed.
_HOOK_FLAGS: dict[str, str] = {
    "beforeSubmitPrompt": "--pre",
    "preToolUse": "--peek",
    "stop": "--post",
}


def _hooks(env: Environment) -> dict[str, str]:
    return {
        event: env.hook_command("cursor-hook", flag)
        for event, flag in _HOOK_FLAGS.items()
    }


# Back-compat alias for callers/tests that just want the event names.
_HOOKS = _HOOK_FLAGS


def _hooks_path(env: Environment | None = None):
    return agent_config_root(AgentName.CURSOR, env) / "hooks.json"


def _load(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_agentnet_cmd(cmd: Any) -> bool:
    return is_agentnet_subcommand(cmd, "cursor-hook")


def _event_has_agentnet(entries: list[Any]) -> bool:
    return any(isinstance(e, dict) and _is_agentnet_cmd(e.get("command")) for e in entries)


def install(env: Environment | None = None) -> tuple[bool, str]:
    """Add AgentNet hooks to ~/.cursor/hooks.json. Return (changed, path)."""
    env = env if env is not None else local_environment()
    path = _hooks_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    changed = False
    for event, command in _hooks(env).items():
        entries = hooks.get(event)
        if not isinstance(entries, list):
            entries = []
            hooks[event] = entries
        if not _event_has_agentnet(entries):
            entries.append({"command": command, "type": "command"})
            changed = True

    if changed:
        from ..infra.config import write_file_safe

        write_file_safe(path, json.dumps(data, indent=2) + "\n")
    return changed, str(path)


def uninstall(env: Environment | None = None) -> tuple[bool, str]:
    """Remove AgentNet hooks from ~/.cursor/hooks.json. Return (changed, path)."""
    env = env if env is not None else local_environment()
    path = _hooks_path(env)
    data = _load(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False, str(path)

    changed = False
    for event in list(_HOOK_FLAGS):
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
        from ..infra.config import write_file_safe

        if not hooks:
            data.pop("hooks", None)
        write_file_safe(path, json.dumps(data, indent=2) + "\n")
    return changed, str(path)
