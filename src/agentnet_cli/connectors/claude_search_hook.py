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


class SettingsHookError(Exception):
    """Raised when ~/.claude/settings.json exists but is malformed, so it must not be overwritten."""


# event -> (command, matcher). matcher=None for non-tool-scoped events.
_HOOKS: dict[str, tuple[str, str | None]] = {
    "UserPromptSubmit": ("agentnet skill-hook --pre", None),
    "PostToolUse": ("agentnet skill-hook --peek", "*"),
    "Stop": ("agentnet skill-hook --post", None),
}


def _settings_path():
    return agent_config_root(AgentName.CLAUDE) / "settings.json"


def _load(path) -> dict[str, Any]:
    """Parse an existing settings.json to a dict.

    Absent file -> ``{}`` (a fresh config). A file that *exists* but is unparseable or not a JSON
    object is NOT the same as empty — overwriting it would erase the user's real config — so raise
    ``SettingsHookError`` and let the caller preserve the file untouched.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise SettingsHookError(f"{path} is not valid JSON — fix it and re-run") from exc
    if not isinstance(data, dict):
        raise SettingsHookError(f"{path} is not a JSON object — fix it and re-run")
    return data


def _is_agentnet_cmd(cmd: Any) -> bool:
    from ..infra.proc import is_agentnet_subcommand  # noqa: PLC0415

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
        path.write_text(json.dumps(data, indent=2) + "\n")
    return changed, str(path)


def uninstall() -> tuple[bool, str]:
    """Remove the AgentNet every-prompt hooks from settings.json. Returns (changed, path).

    A malformed settings file has nothing removable and must not be overwritten, so treat it as
    a no-op rather than raising into the (best-effort) disconnect path.
    """
    path = _settings_path()
    try:
        data = _load(path)
    except SettingsHookError:
        return False, str(path)
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
