"""Install AgentNet hooks in Hermes config.yaml.

This writes three shell hooks: ``pre_llm_call`` starts a discovery worker, ``pre_tool_call`` guides
the agent, and ``pre_verify`` is the fallback. The config is YAML. Each event maps to a list of
``{command, timeout}`` entries. Install is idempotent and keeps existing hooks.

Hermes needs consent for shell hooks. It prompts once per ``(event, command)`` pair and saves
approvals to ``~/.hermes/shell-hooks-allowlist.json``. Non-TTY runs skip unapproved hooks. We
pre-approve our three commands there. This is narrower than the global ``hooks_auto_accept``.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from ..infra.environments import Environment, local_environment
from ..infra.paths import AgentName, agent_config_root
from ..infra.proc import is_agentnet_subcommand

# event -> flag. Timeout is generous but bounded; these hooks only read a cache file (the fallback
# waits ~3s at most), so they never hold up a turn.
_HOOK_FLAGS: dict[str, str] = {
    "pre_llm_call": "--pre",
    "pre_tool_call": "--peek",
    "pre_verify": "--post",
}
_TIMEOUT = 15


def _hooks(env: Environment | None = None) -> dict[str, str]:
    env = env if env is not None else local_environment()
    return {event: env.hook_command("hermes-hook", flag) for event, flag in _HOOK_FLAGS.items()}


# Back-compat alias for callers/tests that just want the event names.
_HOOKS = _HOOK_FLAGS


def _config_path(env: Environment | None = None):
    return agent_config_root(AgentName.HERMES, env) / "config.yaml"


def _allowlist_path(env: Environment | None = None):
    return agent_config_root(AgentName.HERMES, env) / "shell-hooks-allowlist.json"


def _load_yaml(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def _is_agentnet_cmd(cmd: Any) -> bool:
    """Return True only for our hook command.

    Parse the command string. It may be bare, absolute, a Windows ``.exe``, or ``wsl.exe``-bridged.
    Do not use substring matching. Other user hooks may mention agentnet.
    """
    return is_agentnet_subcommand(cmd, "hermes-hook")


def _event_has_agentnet(entries: list[Any]) -> bool:
    return any(isinstance(e, dict) and _is_agentnet_cmd(e.get("command")) for e in entries)


def _sync_allowlist(*, add: bool, env: Environment | None = None) -> None:
    """Pre-approve or remove our hook commands in the Hermes consent allowlist.

    If the allowlist is bad, leave it unchanged. Do not overwrite user approvals.
    """
    env = env if env is not None else local_environment()
    path = _allowlist_path(env)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return
    approvals = data.get("approvals")
    if not isinstance(approvals, list):
        approvals = []
    kept = [
        a
        for a in approvals
        if not (isinstance(a, dict) and _is_agentnet_cmd(a.get("command")))
    ]
    if add:
        kept.extend({"event": event, "command": cmd} for event, cmd in _hooks(env).items())
    data["approvals"] = kept
    try:
        from ..infra.config import write_file_safe

        write_file_safe(path, json.dumps(data, indent=2) + "\n")
    except OSError:
        pass


def install(env: Environment | None = None) -> tuple[bool, str]:
    """Add AgentNet hooks to ~/.hermes/config.yaml and update consent. Return (changed, path)."""
    env = env if env is not None else local_environment()
    path = _config_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_yaml(path)
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
        desired = {"command": command, "timeout": _TIMEOUT}
        # Replace rather than skip: the command string can change between versions (bare ->
        # absolute path). Leaving a stale entry would desync it from the consent allowlist, which
        # keys on the exact string — Hermes then reports "not allowlisted" and never fires it.
        others = [e for e in entries if not (isinstance(e, dict) and _is_agentnet_cmd(e.get("command")))]
        if others + [desired] != entries:
            entries[:] = others + [desired]
            changed = True

    if changed:
        path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    _sync_allowlist(add=True, env=env)
    return changed, str(path)


def uninstall(env: Environment | None = None) -> tuple[bool, str]:
    """Remove AgentNet hooks from ~/.hermes/config.yaml and update consent. Return (changed, path)."""
    env = env if env is not None else local_environment()
    path = _config_path(env)
    data = _load_yaml(path)
    hooks = data.get("hooks")
    _sync_allowlist(add=False, env=env)
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
        path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    return changed, str(path)
