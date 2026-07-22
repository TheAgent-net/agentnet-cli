"""Hermes shell hooks — surface relevant AgentNet skills, reusing the shared skillfire pipeline.

Hermes shell hooks are declared in ``~/.hermes/config.yaml``, run in **both CLI and gateway**, take
a JSON payload on stdin and return JSON on stdout — the same shape as the Claude and Cursor
adapters, so only this thin I/O layer is new. The worker, session cache and atomic once-claims come
straight from the :mod:`agentnet_cli.tools.skillfire` port.

Event mapping (Hermes natively accepts the Claude-Code ``{"decision": "block", ...}`` shape):

- **pre_llm_call** -> ``hermes-hook --pre``: fires once per turn *before* the tool loop — Hermes'
  documented equivalent of Claude's ``UserPromptSubmit``. Spawns the detached worker and returns
  ``{}``. (It *can* inject via ``{"context": …}``, but the worker needs ~20s, so injecting here
  would stall the turn; the steer lands on a later tool call instead.)
- **pre_tool_call** -> ``hermes-hook --peek``: the hard nudge. Returns
  ``{"decision": "block", "reason": …}``, which short-circuits the tool and hands ``reason`` back to
  the model as the tool's error — so the model sees it inline and re-plans. Steer-once.
- **pre_verify** -> ``hermes-hook --post``: fallback, fires when the agent edited code and is about
  to finish. ``{"action": "continue", "message": …}`` appends a synthetic user turn and keeps the
  loop going. Gated on ``extra.attempt`` because it re-fires after each nudge.

Payload: ``{"hook_event_name", "tool_name", "tool_input", "session_id", "cwd", "extra": {...}}``.
Best-effort throughout: any missing field / not-ready cache degrades to ``{}`` (no-op).
"""

from __future__ import annotations

import json
import os
import sys

from . import skillfire


def _session(event: dict) -> str:
    return str(event.get("session_id") or "")


def _extra(event: dict) -> dict:
    extra = event.get("extra")
    return extra if isinstance(extra, dict) else {}


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def run_hermes_pre(*, limit: int, timeout: float) -> None:
    """pre_llm_call: spawn the detached worker for this turn, then get out of the way.

    Spawn-once per (session, prompt) so duplicate registrations spawn one worker; skips our own
    ``[AgentNet]`` continuation so the pre_verify fallback can't loop.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        _emit({})
        return
    event = skillfire.read_event()
    if event is None:
        _emit({})
        return
    session = _session(event)
    prompt = str(_extra(event).get("user_message") or "").strip()
    if not prompt or prompt.startswith(skillfire.AGENTNET_SENTINEL):
        _emit({})  # nothing to do / our own continuation — never re-spawn
        return
    skillfire.spawn_worker(session, prompt, limit=limit, timeout=timeout, classifier="hermes")
    _emit({})


def run_hermes_peek(*, limit: int, timeout: float) -> None:
    """pre_tool_call: hard nudge — block one tool call and hand the skill back to the model.

    ``{}`` allows the call. We only block when the outcome is ready *and* actionable (``final``),
    so we never spend the single steer on a list the agent has nothing to apply from.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        _emit({})
        return
    event = skillfire.read_event()
    if event is None:
        _emit({})
        return
    reason = skillfire.check_steer(_session(event))
    if reason is None:
        _emit({})  # not ready / not actionable / already steered -> allow
        return
    _emit({"decision": "block", "reason": reason})


def run_hermes_post(*, limit: int, timeout: float) -> None:
    """pre_verify: fallback — keep the turn going so the skill still lands.

    Fires only when the agent edited code and is about to finish. Idempotent on ``extra.attempt``:
    Hermes re-fires this after each nudge, so a hook that always continues would just burn the
    ``max_verify_nudges`` budget.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        _emit({})
        return
    event = skillfire.read_event()
    if event is None:
        _emit({})
        return
    if _extra(event).get("attempt"):
        _emit({})  # one-shot: already nudged this turn
        return
    context = skillfire.check_fallback(_session(event), timeout=timeout)
    if context is None:
        _emit({})  # nothing relevant, or a pre_tool_call already steered
        return
    _emit({"action": "continue", "message": context})
