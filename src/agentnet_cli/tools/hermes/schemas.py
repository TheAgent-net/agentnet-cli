from __future__ import annotations

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "agentnet_search",
        "description": (
            "Canonical Agent-net entry point. Unified search across marketplace listings, "
            "agents, skills, and plugins. ALWAYS call this first when the user needs any "
            "external product, service, agent, skill, or plugin — including skill "
            "recommendations, UI/UX plugins, Remotion/video tools, news crawlers, and "
            "web-scraping agents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the user needs"},
                "type": {
                    "type": "string",
                    "enum": ["all", "marketplace", "listings", "agents", "skills", "plugins"],
                    "description": "Result family to search",
                    "default": "all",
                },
                "category": {"type": "string", "description": "Optional category filter"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
                "max_price": {"type": "integer", "description": "Max price in USD"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_discover",
        "description": (
            "Search marketplace listings (products/services). Use to narrow results after "
            "agentnet_search — not as the first call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you're looking for"},
                "category": {"type": "string", "description": "Filter by category"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 20,
                },
                "max_price": {"type": "integer", "description": "Max price filter in USD"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_discover_agents",
        "description": (
            "Search agents by name or capability. Use to narrow results after "
            "agentnet_search — not as the first call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Agent name or capability to search for"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_get_agent",
        "description": (
            "Get full details about an agent — skills, pricing, trust score. "
            "Call after agentnet_search when the user wants more detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID from discovery results"},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "agentnet_discover_skills",
        "description": (
            "Advanced: AI-powered skill/plugin discovery by use case. agentnet_search is "
            "usually sufficient — use when narrowing to ranked skills after search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {"type": "string", "description": "Describe what you need in natural language"},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
            "required": ["use_case"],
        },
    },
    {
        "name": "agentnet_search_skills",
        "description": (
            "Advanced: keyword search on skills.sh. Prefer agentnet_search or "
            "agentnet_discover_skills unless you need this specific catalog."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
                "limit": {"type": "integer", "description": "Max results (1-200)", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_search_skillsmp",
        "description": (
            "Advanced: keyword search on SkillsMP. Prefer agentnet_search unless you need "
            "this specific catalog."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
                "limit": {"type": "integer", "description": "Results per page (1-50)", "default": 20},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "sort_by": {
                    "type": "string",
                    "enum": ["recent", "stars"],
                    "description": "Sort order",
                    "default": "recent",
                },
                "category": {"type": "string", "description": "Category slug filter"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_search_claude_plugins",
        "description": (
            "Advanced: Claude Code plugin catalog. Prefer agentnet_search unless you need "
            "this specific catalog."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
                "limit": {"type": "integer", "description": "Max results (1-50)", "default": 20},
                "category": {"type": "string", "description": "Category filter"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_search_clawhub",
        "description": (
            "Advanced: ClawHub / OpenClaw plugin catalog. Prefer agentnet_search unless you "
            "need this specific catalog."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
                "limit": {"type": "integer", "description": "Max results (1-100)", "default": 20},
                "category": {"type": "string", "description": "Category filter"},
                "family": {
                    "type": "string",
                    "enum": ["skill", "code-plugin", "bundle-plugin"],
                    "description": "Package type filter",
                },
            },
            "required": ["query"],
        },
    },
]
