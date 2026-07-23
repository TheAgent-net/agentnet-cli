"""skillfire — the every-prompt skill-fire pipeline shared by the Claude, Cursor, and Hermes hooks.

This module is **the port**: the only surface a harness adapter (``tools/claude_hook.py``,
``tools/cursor_hook.py``, ``tools/hermes_hook.py``) may import from. Everything else in this
package (``config``, ``session``, ``candidates``, ``classifier``, ``render``, ``content``,
``broker``, ``worker``, ``steer``) is an internal implementation detail, free to change shape
without touching an adapter.

An adapter's three events reduce to three port calls:

- pre-event (submit prompt)  -> :func:`spawn_worker` — launch the detached discovery worker, once.
- mid-run tool call          -> :func:`check_steer` — an actionable, unclaimed outcome's steer
  text, or ``None`` to allow the call.
- turn end / no-tool answer  -> :func:`check_fallback` — the guaranteed fallback steer text, or
  ``None`` if something already steered.

:func:`check_steer_raw`/:func:`check_fallback_raw` make the same decisions but return the bare
outcome with no wrapper text, so a harness can build its own steer wording instead of the shared
``steer_reason``/``fold_context`` framing (used by ``tools/claude_hook.py``).

:func:`run_fetch` is the CLI-invoked entrypoint for the detached worker process itself
(``agentnet skill-hook --fetch``), spawned by :func:`spawn_worker`.
"""

from __future__ import annotations

from .config import AGENTNET_SENTINEL, SUBAGENT_ENV
from .session import prompt_from_event, read_event
from .steer import check_fallback, check_fallback_raw, check_steer, check_steer_raw
from .worker import run_fetch, run_subagent, spawn_worker

__all__ = [
    "AGENTNET_SENTINEL",
    "SUBAGENT_ENV",
    "check_fallback",
    "check_fallback_raw",
    "check_steer",
    "check_steer_raw",
    "prompt_from_event",
    "read_event",
    "run_fetch",
    "run_subagent",
    "spawn_worker",
]
