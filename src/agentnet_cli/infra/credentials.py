"""Get API token, agent id, and platform client from one place.

All Agent-net HTTP code must use these functions. Do not read the token
from the environment or config in other modules.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .config import load_config, save_config
from .platform import get_platform_url

TIER_GUEST = "guest"
TIER_AUTHENTICATED = "authenticated"


def get_api_token(*, config: dict[str, Any] | None = None) -> str:
    """Get the API token from ``AGENTNET_TOKEN`` or local config."""
    token = os.environ.get("AGENTNET_TOKEN", "").strip()
    if token:
        return token
    cfg = config if config is not None else load_config()
    if cfg:
        return str(cfg.get("api_token") or "").strip()
    return ""


def get_agent_id(*, config: dict[str, Any] | None = None) -> str:
    """Get the registered agent id from local config."""
    cfg = config if config is not None else load_config()
    if not cfg:
        return ""
    return str(cfg.get("agent_id") or "").strip()


def get_auth_tier(*, config: dict[str, Any] | None = None) -> str:
    """Return ``guest``, ``authenticated``, or ``\"\"`` when no token is saved."""
    cfg = config if config is not None else load_config()
    if not cfg or not get_api_token(config=cfg):
        return ""
    tier = str(cfg.get("tier") or "").strip().lower()
    if tier in {TIER_GUEST, TIER_AUTHENTICATED}:
        return tier
    # Legacy configs without tier were created via full browser login.
    return TIER_AUTHENTICATED


def is_authenticated(*, config: dict[str, Any] | None = None) -> bool:
    """True when a post-login (elevated) API token is present."""
    return get_auth_tier(config=config) == TIER_AUTHENTICATED


def get_credentials() -> tuple[str, str] | None:
    """Get ``(api_token, platform_url)``, or ``None`` when there is no token.

    The platform URL uses the same rules as :func:`get_platform_url`.
    """
    config = load_config()
    token = get_api_token(config=config)
    if not token:
        return None
    return token, get_platform_url(config=config)


def make_platform_client(
    *,
    timeout: float = 30.0,
    http_client: httpx.Client | None = None,
    require_auth: bool = True,
):
    """Make a :class:`PlatformClient` from shared credentials.

    When *require_auth* is True and there is no token, return ``None``.
    The import is local to avoid a cycle with marketplace at import time.
    """
    from ..marketplace.client import PlatformClient  # noqa: PLC0415

    config = load_config()
    token = get_api_token(config=config)
    if require_auth and not token:
        return None
    url = get_platform_url(config=config)
    return PlatformClient(
        base_url=url,
        api_token=token,
        http_client=http_client or httpx.Client(timeout=timeout),
    )


def ensure_guest_credentials(*, platform_url: str | None = None) -> dict[str, Any]:
    """Ensure a usable API token exists — bootstrap a guest key when needed.

    Returns the saved config. Existing guest or authenticated tokens are kept.
    """
    config = load_config() or {}
    if get_api_token(config=config):
        return config

    from ..marketplace.client import PlatformClient  # noqa: PLC0415

    url = get_platform_url(explicit_url=platform_url, config=config, use_config=True)
    client = PlatformClient(base_url=url)
    try:
        result = client.cli_bootstrap()
    finally:
        client.close()

    token = str(result.get("api_token") or "").strip()
    if not token:
        raise RuntimeError("Platform bootstrap did not return an API token")

    config.update(
        {
            "platform_url": url,
            "api_token": token,
            "org_id": result.get("org_id"),
            "agent_id": result.get("agent_id"),
            "tier": str(result.get("tier") or TIER_GUEST),
        }
    )
    save_config(config)
    return config

