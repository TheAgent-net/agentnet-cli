"""Hook event parsing, session cache, and atomic once-claim primitives.

Shared by every adapter and the detached worker. The cache is keyed by session id because
non-prompt events carry no prompt.
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
    """Read the hook event JSON from stdin. Return ``None`` on error."""
    try:
        event = json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        return None
    return event if isinstance(event, dict) else None


def prompt_from_event(event: dict[str, Any]) -> str:
    """Return the user text from a UserPromptSubmit event."""
    prompt = event.get("prompt")
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else ""


def cache_path(session_id: str) -> Path:
    """Return the session-keyed cache path shared by the worker and hooks.

    Non-prompt events carry no prompt, so all three agree on the session. Prompts are sequential
    per session. The cache holds ``{"outcome": <text>, "final": <bool>}``.
    """
    key = hashlib.sha1((session_id or "default").encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "agentnet-skill" / f"{key}.json"


def cache_read(path: Path) -> dict[str, Any] | None:
    """Read one cache file. Return ``None`` on error."""
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def cache_write(path: Path, outcome: str, *, final: bool = True) -> None:
    """Write the outcome to the cache. ``final`` marks it actionable for steering.

    Phase 1 caches the recommendation list with ``final=False``. Phase 2 rewrites with
    ``final=True`` once SKILL.md content is attached or known to be missing.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"outcome": outcome, "final": final}))
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def claim(marker: Path) -> bool:
    """Create ``marker`` once. Return True only for the caller that created it.

    Hooks may run twice in parallel when registered in more than one config file. ``O_EXCL``
    create is the once-primitive: one caller wins, the rest see the file exists.
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
    """Return the once-per-prompt steer claim path. Cleared by the next ``--pre``."""
    return cache.with_suffix(".emitted")


def spawn_marker(session: str, prompt: str) -> Path:
    """Return the once-per-(session, prompt) worker-spawn claim path."""
    cache = cache_path(session)
    h = hashlib.sha1(prompt.encode()).hexdigest()[:16]
    return cache.parent / f"{cache.stem}.{h}.spawn"


def clear_stale(session: str) -> None:
    """Remove the previous prompt outcome and steer claim."""
    cache = cache_path(session)
    for stale in (cache, emit_marker(cache)):
        try:
            stale.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
