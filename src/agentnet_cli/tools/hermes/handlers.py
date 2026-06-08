from __future__ import annotations

import json
import os
from typing import Any

from agentnet_cli.infra.config import load_config
from agentnet_cli.tools.handlers import ToolHandlers

_NO_TOKEN_ERROR = json.dumps({"error": "Not registered. Run 'agentnet setup' first."})


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


def agentnet_search(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("search", args)


def agentnet_get_agent(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("get_agent", args)







def agentnet_search_skills(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("search_skills", args)


def agentnet_discover_skills(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("discover_skills", args)


def agentnet_search_skillsmp(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("search_skillsmp", args)


def agentnet_search_claude_plugins(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("search_claude_plugins", args)


def agentnet_search_clawhub(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("search_clawhub", args)
