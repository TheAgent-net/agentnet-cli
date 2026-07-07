"""Claude Code hooks — fire AgentNet on every web search, in parallel.

Split across two hook events so the AgentNet fetch overlaps the web search
instead of running after it:

- **PreToolUse** on ``WebSearch`` → ``agentnet hook-slate --pre``: reads the query
  from the tool event and spawns a *detached* worker that fetches the AgentNet
  ``/discover/`` slate and writes it to a cache file, then returns immediately
  (zero added delay). The fetch runs concurrently with the web search.
- **PostToolUse** on ``WebSearch`` → ``agentnet hook-slate --post``: reads the
  cached slate (already fetched during the search) and injects it as
  ``additionalContext``.

Strictly **best-effort**: missing token, empty query, slow/failed platform, or a
not-ready cache all inject nothing and never block, slow, or fail the search.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_LIMIT = 5
DEFAULT_TIMEOUT = 3.0

_DEFAULT_PLATFORM_URL = "https://app.agentnet.market"


def _resolve_credentials() -> tuple[str, str] | None:
    """Resolve (token, platform_url) from env then config, or None. Never exits."""
    from ..infra.config import load_config

    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    if not token:
        return None
    platform_url = _DEFAULT_PLATFORM_URL
    if config:
        platform_url = config.get("platform_url", platform_url)
    return token, platform_url


def _read_event() -> dict[str, Any] | None:
    """Read the hook event JSON from stdin (None on any error)."""
    try:
        event = json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        return None
    return event if isinstance(event, dict) else None


def _query_from_event(event: dict[str, Any]) -> str:
    from .slate import extract_query

    tool_input = event.get("tool_input")
    return extract_query(tool_input) if isinstance(tool_input, dict) else ""


def _cache_path(session_id: str, query: str) -> Path:
    """Deterministic cache path shared by the pre (worker) and post hooks."""
    key = hashlib.sha1(f"{session_id}\n{query}".encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "agentnet-slate" / f"{key}.json"


def build_additional_context(query: str, *, limit: int, timeout: float) -> str:
    """Fetch /discover/ for the query and return the additionalContext envelope.

    Returns "" when there is nothing to inject (no token, no results, any error).
    The request is bounded by ``timeout``.
    """
    if not query:
        return ""
    creds = _resolve_credentials()
    if creds is None:
        return ""
    token, platform_url = creds

    import httpx

    from ..marketplace.client import PlatformClient
    from .slate import format_slate, parse_slate

    platform = PlatformClient(
        base_url=platform_url, api_token=token, http_client=httpx.Client(timeout=timeout)
    )
    try:
        slate_text = format_slate(parse_slate(platform.discover_agents(query=query, limit=limit)))
    except Exception:  # noqa: BLE001 — best-effort: any failure injects nothing
        return ""
    finally:
        platform.close()

    if not slate_text:
        return ""
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": slate_text}}
    )


def run_fetch(*, session: str, query: str, limit: int, timeout: float) -> None:
    """Detached worker: fetch the slate and write it to the cache atomically.

    Always writes a file (possibly empty) so the post hook finds a result quickly
    rather than polling the full timeout.
    """
    payload = build_additional_context(query, limit=limit, timeout=timeout)
    path = _cache_path(session, query)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def run_pre(*, limit: int, timeout: float) -> None:
    """PreToolUse: spawn the detached fetch worker and return immediately."""
    event = _read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    query = _query_from_event(event)
    if not query:
        return
    exe = shutil.which("agentnet") or sys.argv[0]
    try:
        subprocess.Popen(  # noqa: S603 — detached prefetch, never awaited
            [
                exe, "hook-slate", "--fetch",
                "--session", session, "--query", query,
                "--limit", str(limit), "--slate-timeout", str(timeout),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 — best-effort: never block the search
        pass


def run_post(*, limit: int, timeout: float) -> None:
    """PostToolUse: read the prefetched slate and inject it. Never blocks past timeout."""
    event = _read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    query = _query_from_event(event)
    if not query:
        return
    path = _cache_path(session, query)

    deadline = time.monotonic() + timeout
    payload: str | None = None
    while time.monotonic() < deadline:
        if path.exists():
            try:
                payload = path.read_text()
            except Exception:  # noqa: BLE001
                payload = ""
            break
        time.sleep(0.05)

    try:
        path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass

    if payload:
        sys.stdout.write(payload)
        sys.stdout.flush()
