"""Claude Code every-prompt hooks — surface relevant AgentNet skills, token-free.

Three events, so the work overlaps the answer with zero upfront latency and can steer the
live agent mid-flight:

- **UserPromptSubmit** -> ``agentnet skill-hook --pre``: reads the prompt and spawns a
  *detached* skill-scout worker, then returns immediately (no latency).
- **PostToolUse** -> ``agentnet skill-hook --peek``: on each tool call, if the worker's
  outcome is ready and not yet injected, force ``decision:block`` to steer the agent
  mid-flight (inject-once). Exploits the asymmetry: our ~30-60s outcome lands inside the
  agent's minutes-long flow.
- **Stop** -> ``agentnet skill-hook --post``: guaranteed fallback — if nothing steered
  mid-flight (e.g. a no-tool answer), continue the turn (``decision: block`` +
  ``additionalContext``) so the agent applies the skill. Otherwise no-op.

This is the thin I/O adapter for Claude's event shapes; the worker, session cache, and atomic
once-claims live behind the shared :mod:`agentnet_cli.tools.skillfire` port — see that package's
docstring for the full discovery -> classify -> render -> content pipeline.

Claude Code's ``decision:block`` mechanism prints the entire ``reason``/``additionalContext`` text
to the user's terminal transcript (native CLI behavior — the hook's output is shown so the user can
see why a tool call was blocked). Because ``decision:block`` already forces the model to engage —
unlike a soft ``additionalContext`` reminder, which was ignored in practice — this adapter doesn't
need the "STEP 1/2/3, reproduce this fenced block verbatim" scaffolding the shared
``steer_reason``/``fold_context`` (used by Cursor/Hermes) relies on. Instead it builds its **own**
plain-language wording from the raw outcome (via ``skillfire.check_steer_raw``/``check_fallback_raw``,
which hand back the bare outcome with no wrapper): present the list, say what's about to happen, and
trust the block itself to make the model act on it. This also drops the shared "AGENT ONLY — do not
show the user" framing, which is only true for a harness with a genuine hidden channel (Cursor's
``agent_message`` vs ``user_message``) — for Claude nothing is actually hidden, so nothing here
claims otherwise.

Both events also set ``systemMessage`` to the bare skill list — a field Claude Code's hook schema
displays directly to the user and never passes to the model, unlike ``reason``/``additionalContext``.
That makes the list's visibility a platform guarantee rather than something dependent on the model
choosing to relay it. Undocumented for these specific events (``PostToolUse``/``Stop``) as of writing,
so ``reason``/``additionalContext`` still carry the list too, as a fallback if it turns out not to be
honored here.

``claude -p`` inherits the user's hooks; ``AGENTNET_SKILL_SUBAGENT=1`` in the child env makes
the hooks no-op inside the subagent so it can't re-trigger itself.
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
    """Split a shared ``render.compose_outcome()`` payload back into ``(list_block, content)``.

    The cache always stores the fenced form (built once, shared by all three harnesses); this
    reverses it so Claude can present the list and content in its own plain wording instead of the
    shared fenced/STEP format. Read-only reference to render's markers — ``render.py`` itself is
    never modified.
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
    """The "apply the top match" sentence — names the temp SKILL.md path directly when content.py's
    phrasing has one; falls back to the raw content (e.g. the brokered-A2A recommendation, which
    has no on-disk path) otherwise."""
    match = _SKILL_PATH_RE.search(content)
    if match:
        return (
            "apply the top match: its methodology was fetched to a temp file at:\n"
            f"  {match.group(1)}\nRead it and continue with the task."
        )
    return f"apply this recommendation:\n\n{content}"


def _system_message(outcome: str) -> str:
    """The clean list, sent via ``systemMessage`` — displayed to the user directly by Claude Code,
    never passed to the model. Unlike ``reason``/``additionalContext``, this doesn't depend on the
    model choosing to relay anything: it's a platform-guaranteed display, not an instruction.
    """
    list_block, _content = _parse_components(outcome)
    return list_block


def _steer_reason(outcome: str) -> str:
    """Claude's own mid-run steer wording (see module docstring for why this isn't shared).

    Reordering this to lead with "share the list first" didn't change the model's behavior in live
    testing (it still skipped straight to unrelated work either way), so this stays in the simpler
    shape — list right after the intro, one closing instruction. ``systemMessage`` remains the only
    actually-guaranteed channel for the list; nothing in this text can force compliance.
    """
    list_block, content = _parse_components(outcome)
    tail = (
        f"Share this list with the user, then {_apply_tail(content)}"
        if content
        else "Share this list with the user, then continue with the task, applying what those "
        "skills suggest."
    )
    return _NO_SEARCH_PREFIX + list_block + "\n\n" + tail


def _fold_context(outcome: str) -> str:
    """Claude's own turn-end fallback wording (see module docstring for why this isn't shared)."""
    list_block, content = _parse_components(outcome)
    tail = (
        f"Before finishing, share this list with the user, then {_apply_tail(content)}"
        if content
        else "Before finishing, share this list with the user, then apply what those skills "
        "suggest."
    )
    return _NO_SEARCH_PREFIX + list_block + "\n\n" + tail


def run_claude_pre(*, limit: int, timeout: float) -> None:
    """UserPromptSubmit: spawn the detached worker for this prompt, then return immediately.

    Guarded by :func:`skillfire.spawn_worker`'s per-prompt spawn claim so duplicate ``--pre``
    registrations (settings.json + the plugin's ``hooks.json``) spawn exactly one worker.
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
    """PostToolUse: force the agent to consider the skill mid-run (decision:block), once.

    ``decision:block`` + ``reason`` blocks the agentic loop and makes the model address the skill
    *while still running the task* — a soft ``additionalContext`` reminder was ignored in practice.
    """
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
    """Stop: fallback surface for no-tool answers — force the steer at turn end.

    Only fires when nothing already steered mid-run (the shared emit claim), so a tool-using task
    that was hard-nudged already won't also get a fallback.
    """
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
