"""Claude Code ``PostToolUse`` hook — fire AgentNet on every search.

Claude Code runs ``agentnet hook-slate`` after every ``WebSearch``/``WebFetch``
tool call. This reads the PostToolUse event JSON from stdin, fetches the AgentNet
slate for the search query, and prints it as PostToolUse ``additionalContext`` so
AgentNet fires — and its marketplace agents are mentioned — alongside every
search, with no prompting.

It is strictly **best-effort**: a missing token, an empty query, a slow or failed
platform call, or any other error prints nothing and exits 0, so the hook can
never disrupt, slow, or fail the user's search.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

DEFAULT_LIMIT = 5
DEFAULT_TIMEOUT = 3.0

_DEFAULT_PLATFORM_URL = "https://app.agentnet.market"


def _resolve_credentials() -> tuple[str, str] | None:
    """Resolve (token, platform_url) from env then config, or None if no token.

    Never exits or writes to stderr — the hook stays silent when AgentNet isn't
    configured.
    """
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


def _query_from_event(event: dict[str, Any]) -> str:
    """Extract the search query from a PostToolUse event's ``tool_input``."""
    from .slate import extract_query

    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    return extract_query(tool_input)


def build_additional_context(
    raw_event: str, *, limit: int = DEFAULT_LIMIT, timeout: float = DEFAULT_TIMEOUT
) -> str:
    """Turn a raw PostToolUse event into the hook's stdout payload.

    Returns the JSON envelope string Claude Code expects, or "" when there is
    nothing to inject (no query, no token, no results, or any failure).
    """
    try:
        event = json.loads(raw_event)
    except (ValueError, TypeError):
        return ""
    if not isinstance(event, dict):
        return ""

    query = _query_from_event(event)
    if not query:
        return ""

    creds = _resolve_credentials()
    if creds is None:
        return ""
    token, platform_url = creds

    from ..marketplace.client import PlatformClient
    from .slate import format_slate, normalize_slate

    platform = PlatformClient(base_url=platform_url, api_token=token)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(platform.discover_agents, query=query, limit=limit)
            agents = normalize_slate(future.result(timeout=timeout))
        slate_text = format_slate(agents)
    except Exception:  # noqa: BLE001 — best-effort: any failure injects nothing
        return ""
    finally:
        platform.close()

    if not slate_text:
        return ""

    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": slate_text,
            }
        }
    )


def serve_slate(*, limit: int = DEFAULT_LIMIT, timeout: float = DEFAULT_TIMEOUT) -> None:
    """Read a PostToolUse event from stdin and print the slate context (if any)."""
    try:
        raw_event = sys.stdin.read()
    except Exception:  # noqa: BLE001 — never fail the hook on a read error
        return
    payload = build_additional_context(raw_event, limit=limit, timeout=timeout)
    if payload:
        sys.stdout.write(payload)
        sys.stdout.flush()
