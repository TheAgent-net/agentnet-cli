"""Hermes shell hooks — surface relevant AgentNet skills, reusing the Claude/Cursor worker.

Hermes shell hooks are declared in ``~/.hermes/config.yaml``, run in **both CLI and gateway**, take
a JSON payload on stdin and return JSON on stdout — the same shape as the Claude and Cursor
adapters, so only this thin I/O layer is new. The worker (``skill-hook --fetch``), session cache and
atomic once-claims come straight from :mod:`agentnet_cli.tools.hook`.

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
import shutil
import subprocess
import sys
import time

from . import hook as _h

# Tags every injected message; also the loop guard — a pre_verify continuation comes back as a
# synthetic user turn, so --pre must recognise its own text and not re-spawn on it.
_AGENTNET_SENTINEL = "[AgentNet]"


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
    if os.environ.get(_h._SUBAGENT_ENV):
        _emit({})
        return
    event = _h._read_event()
    if event is None:
        _emit({})
        return
    session = _session(event)
    prompt = str(_extra(event).get("user_message") or "").strip()
    if not prompt or prompt.startswith(_AGENTNET_SENTINEL):
        _emit({})  # nothing to do / our own continuation — never re-spawn
        return
    if not _h._claim(_h._spawn_marker(session, prompt)):
        _emit({})  # a duplicate hook already spawned the worker for this prompt
        return
    # Winner: drop the previous turn's outcome + steer claim so this turn starts fresh.
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
                "--classifier", "hermes",  # gate on the user's own Hermes model
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 — best-effort: never block the turn
        pass
    _emit({})


def run_hermes_peek(*, limit: int, timeout: float) -> None:
    """pre_tool_call: hard nudge — block one tool call and hand the skill back to the model.

    ``{}`` allows the call. We only block when the outcome is ready *and* actionable (``final``),
    so we never spend the single steer on a list the agent has nothing to apply from.
    """
    if os.environ.get(_h._SUBAGENT_ENV):
        _emit({})
        return
    event = _h._read_event()
    if event is None:
        _emit({})
        return
    path = _h._cache_path(_session(event))
    data = _h._cache_read(path)
    if not data or not data.get("outcome") or not data.get("final"):
        _emit({})  # not ready / nothing relevant / not yet actionable -> allow
        return
    if not _h._claim(_h._emit_marker(path)):
        _emit({})  # already steered -> allow
        return
    _emit({"decision": "block", "reason": _h._steer_reason(data["outcome"])})


def run_hermes_post(*, limit: int, timeout: float) -> None:
    """pre_verify: fallback — keep the turn going so the skill still lands.

    Fires only when the agent edited code and is about to finish. Idempotent on ``extra.attempt``:
    Hermes re-fires this after each nudge, so a hook that always continues would just burn the
    ``max_verify_nudges`` budget.
    """
    if os.environ.get(_h._SUBAGENT_ENV):
        _emit({})
        return
    event = _h._read_event()
    if event is None:
        _emit({})
        return
    if _extra(event).get("attempt"):
        _emit({})  # one-shot: already nudged this turn
        return
    path = _h._cache_path(_session(event))

    # Short bounded wait for a near-miss; prefer a final (actionable) outcome but take the list if
    # that is all the worker produced — this is the last chance for the turn.
    deadline = time.monotonic() + min(timeout, 3.0)
    data = _h._cache_read(path)
    while (not data or not data.get("outcome") or not data.get("final")) and (
        time.monotonic() < deadline
    ):
        time.sleep(0.1)
        data = _h._cache_read(path)

    outcome = (data or {}).get("outcome") or ""
    if not outcome or not _h._claim(_h._emit_marker(path)):
        _emit({})  # nothing relevant, or a pre_tool_call already steered
        return
    _emit({"action": "continue", "message": _h._fold_context(outcome)})
