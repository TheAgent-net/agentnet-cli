"""Claude Code every-prompt hooks — surface relevant AgentNet skills without a token.

Three events overlap discovery with the answer and can steer the agent mid-flight:

- **UserPromptSubmit** -> ``agentnet skill-hook --pre``: spawn a detached skill-scout worker,
  then return immediately.
- **PostToolUse** -> ``agentnet skill-hook --peek``: when the outcome is ready and not injected,
  return ``decision:block`` to steer mid-flight (inject once).
- **Stop** -> ``agentnet skill-hook --post``: when nothing steered mid-flight, block the turn and
  add context so the agent applies the skill.

This is the thin I/O adapter for Claude event shapes. The worker, session cache, and once-claims
live in :mod:`agentnet_cli.tools.skillfire`.

Claude prints ``reason`` and ``additionalContext`` to the user transcript. This adapter builds
plain-language steer text from the raw outcome with ``check_steer_raw`` and ``check_fallback_raw``.
It does not use the shared ``steer_reason`` or ``fold_context`` wrappers.

Both peek and post also set ``systemMessage`` to the bare skill list. Claude shows that field to
the user and does not pass it to the model.

``claude -p`` inherits the user's hooks. ``AGENTNET_SKILL_SUBAGENT=1`` in the child env makes
hooks no-op inside the subagent.
"""

from __future__ import annotations

import json
import os
import re
import sys

from . import skillfire
from .skillfire import render

_NO_SEARCH_PREFIX = (
    "[AgentNet] Found relevant skills for this task — no need to run your own skill search or "
    "install anything.\n\n"
)
# Matches content.py's own "The full skill methodology is on disk at:\n  <path>" phrasing, so
# Claude's sentence can name the path directly instead of duplicating that wording.
_SKILL_PATH_RE = re.compile(r"on disk at:\s*\n\s*(\S+)")


def _parse_components(outcome: str) -> tuple[str, str]:
    """Split a ``render.compose_outcome()`` payload into ``(list_block, content)``.

    The cache stores the fenced form shared by all harnesses. Reverse it so Claude can use its own
    plain wording.
    """
    start = outcome.find(render.USER_BLOCK_START)
    end = outcome.find(render.USER_BLOCK_END)
    if start == -1 or end == -1:
        return "", outcome  # unexpected shape — surface it as-is rather than lose it
    list_block = outcome[start + len(render.USER_BLOCK_START) : end].strip()
    list_block = list_block.removesuffix("Reading the top match and applying it.").strip()
    agent_idx = outcome.find(render.AGENT_ONLY)
    content = outcome[agent_idx + len(render.AGENT_ONLY) :].strip() if agent_idx != -1 else ""
    return list_block, content


def _apply_tail(content: str) -> str:
    """Return the apply-the-top-match sentence for steer text."""
    match = _SKILL_PATH_RE.search(content)
    if match:
        return (
            "apply the top match: its methodology was fetched to a temp file at:\n"
            f"  {match.group(1)}\nRead it and continue with the task."
        )
    return f"apply this recommendation:\n\n{content}"


def _system_message(outcome: str) -> str:
    """Return the clean list for ``systemMessage`` (user-only display in Claude Code)."""
    list_block, _content = _parse_components(outcome)
    return list_block


def _steer_reason(outcome: str) -> str:
    """Build Claude mid-run steer wording from a raw outcome."""
    list_block, content = _parse_components(outcome)
    tail = (
        f"Share this list with the user, then {_apply_tail(content)}"
        if content
        else "Share this list with the user, then continue with the task, applying what those "
        "skills suggest."
    )
    return _NO_SEARCH_PREFIX + list_block + "\n\n" + tail


def _fold_context(outcome: str) -> str:
    """Build Claude turn-end fallback wording from a raw outcome."""
    list_block, content = _parse_components(outcome)
    tail = (
        f"Before finishing, share this list with the user, then {_apply_tail(content)}"
        if content
        else "Before finishing, share this list with the user, then apply what those skills "
        "suggest."
    )
    return _NO_SEARCH_PREFIX + list_block + "\n\n" + tail


def run_claude_pre(*, limit: int, timeout: float) -> None:
    """Handle UserPromptSubmit: spawn the detached worker, then return immediately.

    ``spawn_worker`` uses a per-prompt spawn claim so duplicate ``--pre`` registrations spawn one
    worker.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return  # inside the subagent — never spawn another
    event = skillfire.read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    prompt = skillfire.prompt_from_event(event)
    if not prompt:
        return
    skillfire.spawn_worker(session, prompt, limit=limit, timeout=timeout, classifier="claude")


def run_claude_peek(*, limit: int, timeout: float) -> None:
    """Handle PostToolUse: block once and steer the agent mid-run with ``decision:block``."""
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return
    event = skillfire.read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    outcome = skillfire.check_steer_raw(session)
    if outcome is None:
        return
    sys.stdout.write(
        json.dumps(
            {
                "decision": "block",
                "reason": _steer_reason(outcome),
                "systemMessage": _system_message(outcome),
            }
        )
    )
    sys.stdout.flush()


def run_claude_post(*, limit: int, timeout: float) -> None:
    """Handle Stop: steer at turn end when nothing steered mid-flight."""
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return
    event = skillfire.read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    outcome = skillfire.check_fallback_raw(session, timeout=timeout)
    if outcome is None:
        return
    sys.stdout.write(
        json.dumps(
            {
                "decision": "block",
                "systemMessage": _system_message(outcome),
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": _fold_context(outcome),
                },
            }
        )
    )
    sys.stdout.flush()
