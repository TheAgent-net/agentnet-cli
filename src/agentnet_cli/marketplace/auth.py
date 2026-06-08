from __future__ import annotations

import json
import os
from typing import Any, NoReturn

from ..infra.config import load_config
from ..infra.platform import resolve_platform_url
from .client import PlatformClient


def get_client() -> PlatformClient:
    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    if not token:
        die("Not authenticated. Run 'agentnet setup' or set AGENTNET_TOKEN.")
    platform_url = resolve_platform_url(config=config)
    return PlatformClient(base_url=platform_url, api_token=token)


def get_agent_id() -> str:
    config = load_config()
    if not config or not config.get("agent_id"):
        die("No agent registered. Run 'agentnet setup' first.")
    return config["agent_id"]


def output(data: Any) -> None:
    print(json.dumps(data, indent=2))


def die(message: str) -> NoReturn:
    print(json.dumps({"error": message}))
    raise SystemExit(1)
