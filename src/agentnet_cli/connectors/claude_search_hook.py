"""Install AgentNet hooks in Claude Code settings.json.

This writes three hooks: ``UserPromptSubmit`` starts a discovery worker, ``PostToolUse`` guides
the agent when results are ready, and ``Stop`` is the fallback. The result matches the bundled
plugin. One command writes ``~/.claude/settings.json`` for any Claude Code version.

``PostToolUse`` uses a ``*`` matcher for all tools. ``UserPromptSubmit`` and ``Stop`` have no
matcher.
"""

from __future__ import annotations

import json
from typing import Any

from ..infra.environments import Environment, local_environment
from ..infra.paths import AgentName, agent_config_root
from ..infra.proc import is_agentnet_subcommand

# event -> (flag, matcher). matcher=None for non-tool-scoped events.
_HOOK_FLAGS: dict[str, tuple[str, str | None]] = {
    "UserPromptSubmit": ("--pre", None),
    "PostToolUse": ("--peek", "*"),
    "Stop": ("--post", None),
}


def _hooks(env: Environment) -> dict[str, tuple[str, str | None]]:
    return {
        event: (env.hook_command("skill-hook", flag), matcher)
        for event, (flag, matcher) in _HOOK_FLAGS.items()
    }


# Back-compat: event names for callers/tests.
_HOOKS = _HOOK_FLAGS


def _settings_path(env: Environment | None = None):
    return agent_config_root(AgentName.CLAUDE, env) / "settings.json"


def _load(path) -> dict[str, Any]:
    """Read settings.json into a dict.

    If the file is missing, return ``{}``. If the file exists but has bad JSON or is not an
    object, raise ``SettingsHookError``. Do not overwrite the user's config.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SettingsHookError(f"{path} is not valid JSON — fix it and re-run") from exc
    if not isinstance(data, dict):
        raise SettingsHookError(f"{path} is not a JSON object — fix it and re-run")
    return data


class SettingsHookError(Exception):
    """Raised when ~/.claude/settings.json exists but is bad. Do not overwrite it."""


def _is_agentnet_cmd(cmd: Any) -> bool:
    return is_agentnet_subcommand(cmd, "skill-hook")


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


def install(env: Environment | None = None) -> tuple[bool, str]:
    """Add UserPromptSubmit and Stop hooks to settings.json. Return (changed, path)."""
    env = env if env is not None else local_environment()
    path = _settings_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    changed = False
    for event, (command, matcher) in _hooks(env).items():
        blocks = hooks.get(event)
        if blocks is None:
            blocks = []
            hooks[event] = blocks
        elif isinstance(blocks, dict):
            # A single hook block stored as an object — preserve it by wrapping, don't discard it.
            blocks = [blocks]
            hooks[event] = blocks
        elif not isinstance(blocks, list):
            # Some other scalar we don't understand — leave the user's value untouched.
            continue
        if not _event_has_agentnet(blocks):
            blocks.append(_block(command, matcher))
            changed = True

    if changed:
        from ..infra.config import write_file_safe

        write_file_safe(path, json.dumps(data, indent=2) + "\n")
    return changed, str(path)


def uninstall(env: Environment | None = None) -> tuple[bool, str]:
    """Remove AgentNet hooks from settings.json. Return (changed, path).

    If settings.json is bad, return unchanged. Do not overwrite the file. Disconnect uses
    best-effort behavior.
    """
    env = env if env is not None else local_environment()
    path = _settings_path(env)
    try:
        data = _load(path)
    except SettingsHookError:
        return False, str(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False, str(path)

    changed = False
    for event in list(_HOOK_FLAGS):
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
        from ..infra.config import write_file_safe

        if not hooks:
            data.pop("hooks", None)
        write_file_safe(path, json.dumps(data, indent=2) + "\n")
    return changed, str(path)
