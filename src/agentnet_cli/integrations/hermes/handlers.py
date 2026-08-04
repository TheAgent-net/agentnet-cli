"""Hermes tool handlers for Agent-net marketplace calls."""

from __future__ import annotations

import json
from typing import Any

from agentnet_cli.infra.credentials import get_credentials, make_platform_client
from agentnet_cli.tools.handlers import ToolActions
from agentnet_cli.tools.tool_defs import TOOL_ACTIONS

_NO_TOKEN_ERROR = json.dumps({"error": "Not registered. Run 'agentnet setup' first."})


def _get_actions() -> ToolActions | None:
    """Return :class:`ToolActions` when credentials exist, else ``None``."""
    creds = get_credentials()
    if creds is None:
        return None
    probe = make_platform_client()
    if probe is None:
        return None
    probe.close()
    token, platform_url = creds
    return ToolActions(
        platform_url=platform_url,
        api_token=token,
    )


def _call(method: str, args: dict[str, Any]) -> str:
    """Call one tool action and return JSON text."""
    try:
        actions = _get_actions()
        if actions is None:
            return _NO_TOKEN_ERROR
        try:
            result = getattr(actions, method)(**args)
            return json.dumps(result)
        finally:
            actions.close()
    except Exception as e:
        return json.dumps({"error": str(e)})


def agentnet_search(args: dict[str, Any], **kwargs: Any) -> str:
    """Handle the ``agentnet_search`` tool."""
    return _call(TOOL_ACTIONS["agentnet_search"], args)
