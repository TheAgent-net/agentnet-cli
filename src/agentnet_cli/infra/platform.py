"""Get the Agent-net platform base URL from CLI flags, env, and config."""

from __future__ import annotations

import os
from typing import Any

PRODUCTION_PLATFORM_URL = "https://app.agentnet.market"
STAGING_PLATFORM_URL = "https://agent-net-server.narun.in"
LOCAL_DEV_PLATFORM_URL = "http://localhost:8000"

_ENV_PLATFORM_URLS: dict[str, str] = {
    "production": PRODUCTION_PLATFORM_URL,
    "prod": PRODUCTION_PLATFORM_URL,
    "staging": STAGING_PLATFORM_URL,
    "stage": STAGING_PLATFORM_URL,
    "development": LOCAL_DEV_PLATFORM_URL,
    "dev": LOCAL_DEV_PLATFORM_URL,
    "local": LOCAL_DEV_PLATFORM_URL,
}

# Backward-compatible alias used by register and docs.
DEFAULT_PLATFORM_URL = PRODUCTION_PLATFORM_URL


def _normalize_url(url: str) -> str:
    """Strip whitespace and a trailing slash from a URL."""
    return url.strip().rstrip("/")


def _env_platform_url() -> str | None:
    """Read an explicit platform URL from the environment."""
    for key in ("AGENTNET_PLATFORM_URL", "AGENTNET_URL"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return _normalize_url(raw)
    return None


def _env_named_platform_url() -> str | None:
    """Map ``AGENTNET_ENV`` to a platform URL."""
    env_name = os.environ.get("AGENTNET_ENV", "").strip().lower()
    if not env_name:
        return None
    return _ENV_PLATFORM_URLS.get(env_name)


def get_platform_url(
    *,
    explicit_url: str | None = None,
    config: dict[str, Any] | None = None,
    use_config: bool = True,
) -> str:
    """Get the Agent-net platform base URL.

    Use this order (highest first):
    1. ``explicit_url`` — CLI ``--url``
    2. ``AGENTNET_PLATFORM_URL`` or ``AGENTNET_URL``
    3. ``AGENTNET_ENV`` map (``development`` / ``staging`` / ``production``)
    4. ``platform_url`` in ``~/.agentnet/config.json`` (when ``use_config`` is True)
    5. Production URL (``https://app.agentnet.market``)
    """
    if explicit_url and explicit_url.strip():
        return _normalize_url(explicit_url)

    env_url = _env_platform_url()
    if env_url:
        return env_url

    named_url = _env_named_platform_url()
    if named_url:
        return named_url

    if use_config and config:
        saved = config.get("platform_url")
        if isinstance(saved, str) and saved.strip():
            return _normalize_url(saved)

    return PRODUCTION_PLATFORM_URL


# Backward-compatible alias for callers not yet migrated to get_platform_url.
resolve_platform_url = get_platform_url
