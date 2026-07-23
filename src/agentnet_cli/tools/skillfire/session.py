"""Hook event parsing, session-keyed cache, and atomic once-claim primitives.

Shared by every adapter (Claude/Cursor/Hermes) and the detached worker. The cache is the only
state shared across a session's pre/peek/post calls, keyed by session id since non-prompt events
(PostToolUse, Stop) carry no prompt.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def read_event() -> dict[str, Any] | None:
    """Read the hook event JSON from stdin (None on any error)."""
    try:
        event = json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        return None
    return event if isinstance(event, dict) else None


def prompt_from_event(event: dict[str, Any]) -> str:
    """The user's text from a UserPromptSubmit event."""
    prompt = event.get("prompt")
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else ""


def cache_path(session_id: str) -> Path:
    """Session-keyed cache shared by the worker and the hooks.

    Non-prompt events (PostToolUse, Stop) carry no prompt, so all three can only agree on the
    session. Prompts are sequential per session, so the session cache holds the current
    prompt's outcome. Stored as ``{"outcome": <text>, "final": <bool>}``.
    """
    key = hashlib.sha1((session_id or "default").encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "agentnet-skill" / f"{key}.json"


def cache_read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def cache_write(path: Path, outcome: str, *, final: bool = True) -> None:
    """Cache the outcome. ``final`` marks it **actionable** (the agent has something to apply).

    Phase 1 caches the recommendation list with ``final=False``: it names skills but carries no
    methodology, so steering on it hands the agent nothing to do. Phase 2 re-writes with
    ``final=True`` once the SKILL.md content is attached (or once we know none is coming).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"outcome": outcome, "final": final}))
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def claim(marker: Path) -> bool:
    """Atomically create ``marker``; return True only for the caller that created it.

    The hooks are registered in both ``settings.json`` and the plugin's ``hooks.json``, so Claude
    Code may run each event's hook twice in parallel. An ``O_EXCL`` create is the atomic
    once-primitive: exactly one of N concurrent callers wins, the rest see the file exists. Used to
    steer once (peek/post) and spawn one worker (pre) regardless of how many copies fire.
    """
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:  # noqa: BLE001 — best-effort: on any error, don't claim (avoid a double)
        return False


def emit_marker(cache: Path) -> Path:
    """Once-per-prompt steer claim (shared by peek + post); cleared by the next ``--pre``."""
    return cache.with_suffix(".emitted")


def spawn_marker(session: str, prompt: str) -> Path:
    """Once-per-(session, prompt) worker-spawn claim, so duplicate ``--pre`` hooks spawn one worker.

    Keyed by the prompt hash — the only thing both parallel ``--pre`` invocations share — so a new
    prompt naturally gets a fresh claim without a reset race.
    """
    cache = cache_path(session)
    h = hashlib.sha1(prompt.encode()).hexdigest()[:16]
    return cache.parent / f"{cache.stem}.{h}.spawn"


def clear_stale(session: str) -> None:
    """Drop the previous prompt's outcome + its steer claim so a new prompt starts fresh."""
    cache = cache_path(session)
    for stale in (cache, emit_marker(cache)):
        try:
            stale.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
