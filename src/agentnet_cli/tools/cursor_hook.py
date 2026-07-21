"""Cursor agent hooks — surface relevant AgentNet skills, reusing the Claude worker.

Cursor's hooks (``~/.cursor/hooks.json``) mirror the Claude three-event flow, but the injection
primitives differ, so only the thin I/O adapter changes — the worker (``skill-hook --fetch``),
session cache, and atomic once-claims are shared verbatim from :mod:`agentnet_cli.tools.hook`.

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
import shutil
import subprocess
import sys
import time

from . import hook as _h

# Prefix on every injected message; also the loop guard — a prompt starting with this is our own
# stop-followup coming back through beforeSubmitPrompt, so --pre skips it instead of re-spawning.
_AGENTNET_SENTINEL = "[AgentNet]"


def _session(event: dict) -> str:
    return str(event.get("conversation_id") or "")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def _deny_message(outcome: str) -> str:
    """Cursor's hard-nudge payload — the same framing as the Claude/Hermes steer.

    Kept as one shared string so a wording fix (e.g. "reproduce the fenced user block exactly")
    lands on every harness at once; they previously drifted and Cursor was the one that never told
    the agent to display the list.
    """
    return _h._steer_reason(outcome)


def run_cursor_pre(*, limit: int, timeout: float) -> None:
    """beforeSubmitPrompt: spawn the detached worker, then allow the prompt.

    Spawn-once per (conversation, prompt) so duplicate registrations spawn one worker; skips our
    own ``[AgentNet]`` stop-followup so the fallback can't loop.
    """
    if os.environ.get(_h._SUBAGENT_ENV):
        _emit({"continue": True})
        return
    event = _h._read_event()
    if event is None:
        _emit({"continue": True})
        return
    prompt = _h._prompt_from_event(event)
    session = _session(event)
    if not prompt or prompt.startswith(_AGENTNET_SENTINEL):
        _emit({"continue": True})  # nothing to do / our own followup — never re-spawn
        return
    if not _h._claim(_h._spawn_marker(session, prompt)):
        _emit({"continue": True})  # a duplicate --pre already spawned the worker
        return
    # Winner: drop the previous prompt's outcome + steer claim so this prompt starts fresh.
    cache = _h._cache_path(session)
    for stale in (cache, _h._emit_marker(cache)):
        try:
            stale.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    exe = shutil.which("agentnet") or sys.argv[0]
    try:
        subprocess.Popen(  # noqa: S603 — detached discovery, never awaited
            [
                exe, "skill-hook", "--fetch",
                "--session", session, "--query", prompt,
                "--limit", str(limit), "--timeout", str(timeout),
                "--classifier", "cursor",  # gate on the user's Cursor model, not claude
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 — best-effort: never block the prompt
        pass
    _emit({"continue": True})


def run_cursor_peek(*, limit: int, timeout: float) -> None:
    """preToolUse: hard nudge — deny the first tool call once and feed the skill to the agent.

    No output (exit 0) allows the action. We only deny when the outcome is ready and the shared
    emit claim is still open, so exactly one tool call is denied; the agent reads + applies the
    skill and retries, and the retry is allowed.
    """
    if os.environ.get(_h._SUBAGENT_ENV):
        return
    event = _h._read_event()
    if event is None:
        return  # allow
    session = _session(event)
    path = _h._cache_path(session)
    data = _h._cache_read(path)
    if not data or not data.get("outcome"):
        return  # not ready / nothing relevant -> allow
    if not data.get("final"):
        return  # phase-1 list only — denying now would hand the agent nothing to apply
    if not _h._claim(_h._emit_marker(path)):
        return  # already steered (peek/post/duplicate) -> allow
    _emit(
        {
            "permission": "deny",
            "agent_message": _deny_message(data["outcome"]),
            "user_message": "AgentNet: applying a relevant skill for this task",
        }
    )


def run_cursor_post(*, limit: int, timeout: float) -> None:
    """stop: fallback surface for no-tool answers via a ``[AgentNet]``-tagged followup message.

    Fires only when nothing already steered (the shared emit claim), so a tool-using task that was
    hard-nudged mid-run won't also get a followup.
    """
    if os.environ.get(_h._SUBAGENT_ENV):
        return
    event = _h._read_event()
    if event is None:
        return
    session = _session(event)
    path = _h._cache_path(session)

    # Short bounded wait for a near-miss. Prefer a final (actionable) outcome, but this is the last
    # chance for the turn — take the recommendation list if that's all the worker produced.
    deadline = time.monotonic() + min(timeout, 3.0)
    data = _h._cache_read(path)
    while (not data or not data.get("outcome") or not data.get("final")) and (
        time.monotonic() < deadline
    ):
        time.sleep(0.1)
        data = _h._cache_read(path)

    outcome = (data or {}).get("outcome") or ""
    if not outcome or not _h._claim(_h._emit_marker(path)):
        return  # nothing relevant, or a preToolUse/duplicate already steered
    _emit({"followup_message": _h._fold_context(outcome)})
