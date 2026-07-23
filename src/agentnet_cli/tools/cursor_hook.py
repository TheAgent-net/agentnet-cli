"""Cursor agent hooks — surface relevant AgentNet skills, reusing the shared skillfire pipeline.

Cursor's hooks (``~/.cursor/hooks.json``) mirror the Claude three-event flow, but the injection
primitives differ, so only the thin I/O adapter changes — the worker, session cache, and atomic
once-claims are shared verbatim via the :mod:`agentnet_cli.tools.skillfire` port.

- **beforeSubmitPrompt** -> ``cursor-hook --pre``: spawn the detached worker, then allow the
  prompt (``{"continue": true}``). This event can only allow/block — it cannot inject — so it is
  spawn-only, exactly like the Claude ``--pre``.
- **preToolUse** -> ``cursor-hook --peek``: the **hard nudge**. Cursor's only forceful steer is a
  denied action, so once the worker's outcome is ready we deny the first tool call *once*
  (``{"permission": "deny", "agent_message": …}``) — the agent must read + apply the skill, then
  retry. Deny-once via the shared emit claim; every later call is allowed (no output).
- **stop** -> ``cursor-hook --post``: guaranteed fallback for no-tool answers via
  ``followup_message`` (auto-submitted as the next user turn). The message is ``[AgentNet]``-tagged
  so the re-fired ``--pre`` recognises its own injection and does not loop.

Session key is Cursor's ``conversation_id`` (present on all three events). Best-effort throughout:
any missing field / not-ready cache degrades to allowing the action untouched.
"""

from __future__ import annotations

import json
import os
import sys

from . import skillfire


def _session(event: dict) -> str:
    return str(event.get("conversation_id") or "")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def run_cursor_pre(*, limit: int, timeout: float) -> None:
    """beforeSubmitPrompt: spawn the detached worker, then allow the prompt.

    Spawn-once per (conversation, prompt) so duplicate registrations spawn one worker; skips our
    own ``[AgentNet]`` stop-followup so the fallback can't loop.
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
    """preToolUse: hard nudge — deny the first tool call once and feed the skill to the agent.

    No output (exit 0) allows the action. We only deny when the outcome is ready, actionable, and
    the shared emit claim is still open, so exactly one tool call is denied; the agent reads +
    applies the skill and retries, and the retry is allowed.
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
    """stop: fallback surface for no-tool answers via a ``[AgentNet]``-tagged followup message.

    Fires only when nothing already steered (the shared emit claim), so a tool-using task that was
    hard-nudged mid-run won't also get a followup.
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
