"""opencode plugin adapter — surface relevant AgentNet skills, reusing the shared skillfire pipeline.

opencode plugins run in-process under Bun, so the bundled JS plugin
(``integrations/opencode/agentnet.js``) holds the event in-process and shells out to these commands,
passing ``--session``/``--query`` as CLI args — unlike the Claude/Cursor/Hermes shell hooks, which
read a stdin event. Only this thin I/O adapter differs; the worker, session cache, and atomic
once-claims are shared verbatim via the :mod:`agentnet_cli.tools.skillfire` port.

opencode has two constraints the other harnesses don't, both handled here (learned from a live run):

- **The system prompt is invisible to the user**, and it sandboxes tool reads to the project dir —
  so a "read the SKILL.md on disk at <temp path>" pointer (what the shared outcome injects for
  Claude) is both unseen *and* unreadable (opencode auto-rejects the external-directory read). So
  ``--peek`` **inlines** the skill methodology (read from that temp file, on the Python side where
  there is no sandbox) directly into the system-prompt text.
- **Injection is invisible**, so the user needs a separate signal: ``--peek`` emits a two-part
  payload ``<toast-list>\x1e<system-prompt-text>``; the plugin shows ``<toast-list>`` as a toast
  (so the user sees which skills fired) and pushes ``<system-prompt-text>`` onto ``output.system``.

Best-effort throughout: nothing printed / exit 0 on any issue.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from . import skillfire
from .skillfire import render
from .skillfire import session as _session

# Record separator between the user-facing toast text and the model-facing system-prompt text.
_RS = "\x1e"
# Matches content.py's "…is on disk at:\n  <path>…" pointer so we can inline the file instead.
_PATH_RE = re.compile(r"[^\n]*on disk at:\s*\n\s*(\S+)[^\n]*(?:\n[^\n]*)?", re.IGNORECASE)
_MAX_INLINE = 8000  # cap the inlined methodology so the system prompt stays bounded


def _components(outcome: str) -> tuple[str, str]:
    """Split a composed outcome into ``(list_block, content)`` using render's markers.

    ``('', outcome)`` if the fenced shape is absent (defensive). Read-only reference to render's
    markers — ``render.py`` is never modified.
    """
    start = outcome.find(render.USER_BLOCK_START)
    end = outcome.find(render.USER_BLOCK_END)
    if start == -1 or end == -1:
        return "", outcome
    list_block = outcome[start + len(render.USER_BLOCK_START) : end].strip()
    list_block = list_block.removesuffix("Reading the top match and applying it.").strip()
    agent = outcome.find(render.AGENT_ONLY)
    content = outcome[agent + len(render.AGENT_ONLY) :].strip() if agent != -1 else ""
    return list_block, content


def _inline(content: str) -> str:
    """Replace an "on disk at: <path>" pointer with the file's actual text.

    opencode can't read our temp SKILL.md (external-dir sandbox), so hand the model the methodology
    directly. Falls back to ``content`` as-is when there's no on-disk pointer (e.g. the brokered-A2A
    recommendation, which is already inline text).
    """
    match = _PATH_RE.search(content)
    if not match:
        return content
    try:
        methodology = Path(match.group(1)).read_text()[:_MAX_INLINE]
    except Exception:  # noqa: BLE001 — best-effort; keep the pointer text if the file's gone
        return content
    header = content[: match.start()].strip()  # the "name — description" line(s)
    return f"{header}\n\n{methodology}".strip()


def _toast_marker(path: Path) -> Path:
    """Once-per-prompt toast claim — sibling to the steer's ``.emitted`` marker, so the user-facing
    toast (phase-1 list) and the model-facing steer (phase-2 methodology) fire independently."""
    return path.with_suffix(".toasted")


def _system_text(body: str) -> str:
    return (
        "You have access to a proven AgentNet marketplace skill for this task. "
        "Apply this methodology as you work:\n\n" + body
    )


def run_opencode_pre(session: str, prompt: str, *, limit: int, timeout: float) -> None:
    """chat.message: spawn the detached worker for this prompt, then return immediately.

    Skips our own ``[AgentNet]`` text so it can never re-spawn on itself.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return  # inside the gate subagent — never spawn another
    if not prompt or prompt.startswith(skillfire.AGENTNET_SENTINEL):
        return
    skillfire.spawn_worker(session, prompt, limit=limit, timeout=timeout, classifier="opencode")


def run_opencode_peek(session: str, *, limit: int, timeout: float) -> None:
    """system.transform: emit ``<toast>\x1e<system-text>`` (JS toasts the list, injects the text).

    Two independent once-claims, because opencode's steer (system prompt) is invisible and its
    content lands ~40s in, while its list is ready ~15s in:

    - **Toast (visibility):** the moment the phase-1 list exists, toast it once (``.toasted``) so the
      user sees which skills fired *mid-turn* — not gated on ``final``.
    - **Steer (action):** once the outcome is ``final`` (methodology inlined), inject it once
      (``.emitted``). Fires only if the turn lasts long enough to reach a later inference.

    Either part may be empty; nothing is printed when there's nothing new to do.
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return
    path = _session.cache_path(session)
    data = _session.cache_read(path)
    outcome = (data or {}).get("outcome") or ""
    if not outcome:
        return
    list_block, content = _components(outcome)

    toast = list_block if (list_block and _session.claim(_toast_marker(path))) else ""
    system = ""
    if (data or {}).get("final") and _session.claim(_session.emit_marker(path)):
        system = _system_text(_inline(content) if content else list_block)

    if not toast and not system:
        return
    sys.stdout.write(toast + _RS + system)
    sys.stdout.flush()


def run_opencode_post(session: str, *, limit: int, timeout: float) -> None:
    """session.idle: toast the skill list — a non-polling fallback for turns shorter than the worker.

    The turn is over, so there's no inference left to steer. **Non-polling on purpose:** opencode
    disposes the instance right after ``session.idle``, so a blocking wait (like the shared
    ``check_fallback``) wouldn't return before the toast could show. Reads the cache once and toasts
    the list if it exists and wasn't already toasted mid-turn (shared ``.toasted`` claim).
    """
    if os.environ.get(skillfire.SUBAGENT_ENV):
        return
    path = _session.cache_path(session)
    data = _session.cache_read(path)
    outcome = (data or {}).get("outcome") or ""
    if not outcome:
        return
    list_block, _content = _components(outcome)
    if list_block and _session.claim(_toast_marker(path)):
        sys.stdout.write(list_block)
        sys.stdout.flush()
