"""Hermes shell hooks — surface relevant AgentNet skills with the shared skillfire pipeline.

Hermes shell hooks are declared in ``~/.hermes/config.yaml``. They run in CLI and gateway, read
JSON from stdin, and write JSON to stdout. The worker, session cache, and once-claims come from
:mod:`agentnet_cli.tools.skillfire`.

Event mapping (Hermes accepts Claude-style ``{"decision": "block", ...}``):

- **pre_llm_call** -> ``hermes-hook --pre``: spawn the detached worker and return ``{}``.
- **pre_tool_call** -> ``hermes-hook --peek``: return ``{"decision": "block", "reason": …}`` once.
- **pre_verify** -> ``hermes-hook --post``: return ``{"action": "continue", "message": …}`` as a
  fallback when the agent is about to finish. Gated on ``extra.attempt``.

Payload: ``{"hook_event_name", "tool_name", "tool_input", "session_id", "cwd", "extra": {...}}``.
Missing fields or a not-ready cache return ``{}`` (no-op).
"""

from __future__ import annotations

import json
import os
import sys

from . import skillfire


def _session(event: dict) -> str:
    """Return the session id from a Hermes hook event."""
    return str(event.get("session_id") or "")


def _extra(event: dict) -> dict:
    """Return the ``extra`` dict from a Hermes hook event."""
    extra = event.get("extra")
    return extra if isinstance(extra, dict) else {}


def _emit(obj: dict) -> None:
    """Write one JSON response to stdout."""
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def run_hermes_pre(*, limit: int, timeout: float) -> None:
    """Handle pre_llm_call: spawn the detached worker for this turn, then return ``{}``.

    Spawn once per (session, prompt). Skip ``[AgentNet]`` continuations so fallback cannot loop.
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
    """Handle pre_tool_call: block one tool call and hand the skill back to the model.

    Return ``{}`` to allow the call. Block only when the outcome is ready and actionable.
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
    """Handle pre_verify: keep the turn going so the skill still lands.

    Fire when the agent edited code and is about to finish. Skip when ``extra.attempt`` is set.
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
