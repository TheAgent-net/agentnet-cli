from __future__ import annotations

import json
import os
from typing import Any

from ..config import load_config
from ..mcp.tools import ToolHandlers

_NO_TOKEN_ERROR = json.dumps({"error": "Not registered. Run 'agentnet register' first."})


def _get_handlers() -> ToolHandlers | None:
    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    platform_url = (config or {}).get("platform_url", "https://app.agentnet.market")
    agent_id = (config or {}).get("agent_id", "")
    if not token:
        return None
    return ToolHandlers(
        platform_url=platform_url,
        api_token=token,
        agent_id=agent_id,
    )


def _call(method: str, args: dict[str, Any]) -> str:
    try:
        h = _get_handlers()
        if h is None:
            return _NO_TOKEN_ERROR
        result = getattr(h, method)(**args)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def agentnet_discover(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("discover", args)


def agentnet_discover_agents(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("discover_agents", args)


def agentnet_get_agent(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("get_agent", args)


def agentnet_use_agent(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("use_agent", args)


def agentnet_continue_session(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("continue_session", args)


def agentnet_settle_session(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("settle_session", args)


def agentnet_wallet(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("wallet", args)


def agentnet_wallet_topup(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("wallet_topup", args)
