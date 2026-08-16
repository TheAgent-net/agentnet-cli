"""Tool specs for MCP and Hermes — one search tool."""

from __future__ import annotations

from typing import Any

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "agentnet_search",
        "description": (
            "Search Agent-net for agents, skills, plugins, and listings. "
            "Call this when the user needs an external agent or skill."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the user needs"},
                "type": {
                    "type": "string",
                    "enum": ["all", "agents", "skills", "plugins", "listings", "marketplace"],
                    "description": "Result family to search",
                    "default": "all",
                },
                "category": {"type": "string", "description": "Optional category filter"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": ["query"],
        },
    },
]

TOOL_ACTIONS: dict[str, str] = {
    "agentnet_search": "search",
}


def mcp_tool_specs() -> list[dict[str, Any]]:
    """Return tool specs in MCP shape (``inputSchema``)."""
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["parameters"],
        }
        for tool in TOOL_SPECS
    ]
