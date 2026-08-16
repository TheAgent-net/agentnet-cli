"""Skillfire public port for Claude, Cursor, and Hermes hooks.

Harness adapters may import only this module from skillfire. Other skillfire
modules are internal.

Adapter events map to three port calls:

- pre-event (submit prompt) -> :func:`spawn_worker` — start the detached worker once.
- mid-run tool call -> :func:`check_steer` — return steer text, or ``None`` to allow the call.
- turn end / no-tool answer -> :func:`check_fallback` — return fallback steer text, or ``None``.

:func:`check_steer_raw` and :func:`check_fallback_raw` return the bare outcome with no
wrapper text. Harnesses can build their own steer wording.

:func:`run_fetch` is the CLI entry for the detached worker (``agentnet skill-hook --fetch``).
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
