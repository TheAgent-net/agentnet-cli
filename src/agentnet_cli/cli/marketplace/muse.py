from __future__ import annotations

import os

import typer

from ...infra.config import load_config
from ...infra.platform import resolve_platform_url
from ...marketplace.auth import die, output


def _mask(token: str) -> str:
    return token[:9] + "…" + token[-4:] if len(token) > 16 else "…"


def muse(
    show_key: bool = typer.Option(
        False, "--show-key", help="Print the full API key (to paste into Muse's credential prompt)",
    ),
) -> None:
    """Print the settings that add AgentNet Concierge to Meta Muse as a custom connector."""
    config = load_config()
    token = os.environ.get("AGENTNET_TOKEN", "") or (config or {}).get("api_token", "")
    if not token:
        die("Not authenticated. Run 'agentnet setup' or set AGENTNET_TOKEN.")
    base = resolve_platform_url(config=config)
    mcp_url = f"{base}/muse/mcp"
    output({
        "name": "AgentNet Concierge",
        "mcp_url": mcp_url,
        "transport": "streamable-http",
        "auth": "bearer",
        "api_key": token if show_key else _mask(token),
        "muse_prompt": (
            f"Connect a custom connector to the MCP server at {mcp_url} using bearer-token "
            "auth. I'll enter the token in the secure credential prompt."
        ),
        "policy_url": f"{base}/muse/policy",
    })
