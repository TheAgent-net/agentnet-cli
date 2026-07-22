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

This is the thin I/O adapter for Claude's event shapes; the worker, session cache, atomic
once-claims, and steer-text all live behind the shared :mod:`agentnet_cli.tools.skillfire` port —
see that package's docstring for the full discovery -> classify -> render -> content pipeline.

``claude -p`` inherits the user's hooks; ``AGENTNET_SKILL_SUBAGENT=1`` in the child env makes
the hooks no-op inside the subagent so it can't re-trigger itself.
"""

from __future__ import annotations

import json
import os
import sys

from . import skillfire


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
    reason = skillfire.check_steer(session)
    if reason is None:
        return
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
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
    context = skillfire.check_fallback(session, timeout=timeout)
    if context is None:
        return
    sys.stdout.write(
        json.dumps(
            {
                "decision": "block",
                "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": context},
            }
        )
    )
    sys.stdout.flush()
