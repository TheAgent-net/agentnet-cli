"""Auth helpers for marketplace CLI commands."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from ..infra.credentials import get_agent_id as _get_agent_id
from ..infra.credentials import make_platform_client
from .client import PlatformClient


def get_client() -> PlatformClient:
    """Return an authenticated :class:`PlatformClient`. Exit when not authenticated."""
    client = make_platform_client()
    if client is None:
        die("Not authenticated. Run 'agentnet setup' or set AGENTNET_TOKEN.")
    return client


def get_agent_id() -> str:
    """Return the registered agent id. Exit when none is registered."""
    agent_id = _get_agent_id()
    if not agent_id:
        die("No agent registered. Run 'agentnet setup' first.")
    return agent_id


def output(data: Any) -> None:
    """Print JSON data to stdout."""
    print(json.dumps(data, indent=2))


def die(message: str) -> NoReturn:
    """Print a JSON error and exit with code 1."""
    print(json.dumps({"error": message}))
    raise SystemExit(1)
