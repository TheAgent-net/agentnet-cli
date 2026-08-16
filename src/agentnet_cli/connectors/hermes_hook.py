"""Install the AgentNet skill-fire hooks into Hermes' ``~/.hermes/config.yaml``.

Registers three shell hooks mirroring the Claude/Cursor flow — ``pre_llm_call`` (spawn the
background discovery worker), ``pre_tool_call`` (hard nudge) and ``pre_verify`` (fallback when the
agent edited code and is about to finish).

Two Hermes specifics:

- The config is **YAML** (not JSON), and each event maps to a list of ``{command, timeout}`` entries
  (``matcher`` applies to pre/post_tool_call only — we enforce steer-once in the hook itself, so no
  matcher is needed). Install is idempotent and preserves any hooks the user already has.
- Shell hooks require **consent**: Hermes prompts once per ``(event, command)`` pair and persists it
  to ``~/.hermes/shell-hooks-allowlist.json``. Non-TTY runs (gateway, cron, CI) *silently skip*
  un-approved hooks, so we pre-approve our own three commands there. That is deliberately narrower
  than flipping the global ``hooks_auto_accept``, which would auto-approve *any* hook.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

import yaml

from ..infra.paths import AgentName, agent_config_root

# event -> flag. Timeout is generous but bounded; these hooks only read a cache file (the fallback
# waits ~3s at most), so they never hold up a turn.
_HOOK_FLAGS: dict[str, str] = {
    "pre_llm_call": "--pre",
    "pre_tool_call": "--peek",
    "pre_verify": "--post",
}
_TIMEOUT = 15


def _agentnet_bin() -> str:
    """Absolute path to the agentnet binary when resolvable, else the bare command.

    ``hermes hooks doctor`` stats the command's first token to check the exec bit, so a bare
    ``agentnet`` is reported as "script missing or not executable" even though it runs fine. Same
    resolution the Cursor MCP writer uses.
    """
    return shutil.which("agentnet") or "agentnet"


def _hooks() -> dict[str, str]:
    exe = _agentnet_bin()
    return {event: f"{exe} hermes-hook {flag}" for event, flag in _HOOK_FLAGS.items()}


# Back-compat alias for callers/tests that just want the event names.
_HOOKS = _HOOK_FLAGS


def _config_path():
    return agent_config_root(AgentName.HERMES) / "config.yaml"


def _allowlist_path():
    return agent_config_root(AgentName.HERMES) / "shell-hooks-allowlist.json"


def _load_yaml(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def _is_agentnet_cmd(cmd: Any) -> bool:
    """True only for *our* hook command.

    Parsed rather than substring-matched: the command may be bare (``agentnet hermes-hook …``),
    absolute (``/usr/local/bin/agentnet hermes-hook …``), or Windows-style
    (``C:\\…\\agentnet.EXE hermes-hook …``) depending on what ``which`` resolved at install time.
    A substring test would also claim an unrelated user hook that merely mentions it
    (e.g. ``/opt/wrapper.sh --run "agentnet hermes-hook --pre"``) — install would replace it and
    uninstall would revoke its consent.
    """
    from ..infra.proc import is_agentnet_subcommand  # noqa: PLC0415

    return is_agentnet_subcommand(cmd, "hermes-hook")


def _event_has_agentnet(entries: list[Any]) -> bool:
    return any(isinstance(e, dict) and _is_agentnet_cmd(e.get("command")) for e in entries)


def _sync_allowlist(*, add: bool) -> None:
    """Pre-approve (or revoke) our own hook commands in Hermes' consent allowlist.

    Best-effort: a malformed allowlist is left untouched rather than clobbered — losing a user's
    approvals would silently disable their other hooks.
    """
    path = _allowlist_path()
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
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
        kept.extend({"event": event, "command": cmd} for event, cmd in _hooks().items())
    data["approvals"] = kept
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError:
        pass


def install() -> tuple[bool, str]:
    """Add the AgentNet hooks to ~/.hermes/config.yaml (+ consent). Returns (changed, path)."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_yaml(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    changed = False
    for event, command in _hooks().items():
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
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    _sync_allowlist(add=True)
    return changed, str(path)


def uninstall() -> tuple[bool, str]:
    """Remove the AgentNet hooks from ~/.hermes/config.yaml (+ consent). Returns (changed, path)."""
    path = _config_path()
    data = _load_yaml(path)
    hooks = data.get("hooks")
    _sync_allowlist(add=False)
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
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return changed, str(path)
