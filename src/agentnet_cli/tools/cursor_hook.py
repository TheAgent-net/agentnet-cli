"""Cursor agent hooks — surface relevant AgentNet skills with the shared skillfire pipeline.

Cursor hooks in ``~/.cursor/hooks.json`` mirror the Claude three-event flow. Only the I/O adapter
changes. The worker, session cache, and once-claims come from :mod:`agentnet_cli.tools.skillfire`.

- **beforeSubmitPrompt** -> ``cursor-hook --pre``: spawn the detached worker, then allow the
  prompt (``{"continue": true}``). This event cannot inject, so it is spawn-only.
- **preToolUse** -> ``cursor-hook --peek``: deny the first tool call once when the outcome is
  ready (``{"permission": "deny", "agent_message": …}``). Later calls are allowed.
- **stop** -> ``cursor-hook --post``: fallback for no-tool answers with a ``[AgentNet]``-tagged
  ``followup_message``. The re-fired ``--pre`` recognizes the tag and does not loop.

Session key is Cursor's ``conversation_id``. Missing fields or a not-ready cache allow the action.
"""

from __future__ import annotations

import json
import os
import sys

from . import skillfire


def _session(event: dict) -> str:
    """Return the conversation id from a Cursor hook event."""
    return str(event.get("conversation_id") or "")


def _emit(obj: dict) -> None:
    """Write one JSON response to stdout."""
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def run_cursor_pre(*, limit: int, timeout: float) -> None:
    """Handle beforeSubmitPrompt: spawn the detached worker, then allow the prompt.

    Spawn once per (conversation, prompt). Skip ``[AgentNet]`` followups so fallback cannot loop.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        _emit({"continue": True})
        return
    event = skillfire.read_event()
    if event is None:
        _emit({"continue": True})
        return
    prompt = skillfire.prompt_from_event(event)
    session = _session(event)
    if not prompt or prompt.startswith(skillfire.AGENTNET_SENTINEL):
        _emit({"continue": True})  # nothing to do / our own followup — never re-spawn
        return
    skillfire.spawn_worker(session, prompt, limit=limit, timeout=timeout, classifier="cursor")
    _emit({"continue": True})


def run_cursor_peek(*, limit: int, timeout: float) -> None:
    """Handle preToolUse: deny the first tool call once and feed the skill to the agent.

    No output allows the action. Deny only when the outcome is ready, actionable, and unclaimed.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return
    event = skillfire.read_event()
    if event is None:
        return  # allow
    reason = skillfire.check_steer(_session(event))
    if reason is None:
        return  # not ready / not actionable / already steered -> allow
    _emit(
        {
            "permission": "deny",
            "agent_message": reason,
            "user_message": "AgentNet: applying a relevant skill for this task",
        }
    )


def run_cursor_post(*, limit: int, timeout: float) -> None:
    """Handle stop: fallback for no-tool answers with a ``[AgentNet]`` followup message.

    Fire only when nothing already steered mid-flight.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return
    event = skillfire.read_event()
    if event is None:
        return
    context = skillfire.check_fallback(_session(event), timeout=timeout)
    if context is None:
        return  # nothing relevant, or a preToolUse/duplicate already steered
    _emit({"followup_message": context})
