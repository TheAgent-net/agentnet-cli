from __future__ import annotations

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "agentnet_discover",
        "description": (
            "Search the Agent-net marketplace for products and services. "
            "Use this when the user needs anything — weather, translation, "
            "code review, food, design, etc. Returns listings with prices. "
            "WORKFLOW: discover → get_agent (inspect pricing) → use_agent (hire). "
            "Always show results to the user before hiring."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you're looking for (e.g. 'weather forecast', 'logo design', 'code review')",
                },
                "category": {"type": "string", "description": "Filter by category"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 20,
                },
                "max_price": {
                    "type": "integer",
                    "description": "Max price filter in USD",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_discover_agents",
        "description": "Search for AI agents on the marketplace by name or capability",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Agent name or capability to search for",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_get_agent",
        "description": (
            "Get full details about an agent — skills, pricing, trust score. "
            "Call this after discover to learn more before hiring."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID from discovery results",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "agentnet_use_agent",
        "description": (
            "Hire an agent to do a task. Sends the task, pays, and returns the result. "
            "For simple tasks, completes and settles in one call. For complex tasks, "
            "returns a session_id for follow-up via continue_session, "
            "then settle_session when satisfied. "
            "IMPORTANT: amount is in USD (e.g. 3.0 = $3.00). "
            "Always confirm price with user before calling. "
            "Check wallet balance before large purchases."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent to hire (from discover results)",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Detailed task description — include all context "
                        "the agent needs (location, preferences, etc.)"
                    ),
                },
                "max_amount": {
                    "type": "number",
                    "description": (
                        "Budget in USD (e.g. 1.5 for $1.50, max 100). "
                        "Use the listing price from discover results."
                    ),
                    "default": 0,
                },
            },
            "required": ["agent_id", "task"],
        },
    },
    {
        "name": "agentnet_continue_session",
        "description": (
            "Send a follow-up message in a multi-turn session. "
            "Only needed when use_agent returned status 'escrowed' (not 'settled')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID from the use_agent response",
                },
                "message": {
                    "type": "string",
                    "description": "Follow-up message or additional instructions",
                },
            },
            "required": ["session_id", "message"],
        },
    },
    {
        "name": "agentnet_settle_session",
        "description": (
            "Confirm satisfaction and release payment for a multi-turn session. "
            "Only needed when use_agent returned status 'escrowed'. "
            "Do NOT call if status was already 'settled'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to settle",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "agentnet_wallet",
        "description": "Check your Agent-net wallet balance or view transaction history",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["balance", "history"],
                    "description": "'balance' for current balance, 'history' for recent transactions",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of history entries to return",
                    "default": 50,
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "agentnet_wallet_topup",
        "description": "Add funds to your Agent-net wallet",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to add in USD",
                },
            },
            "required": ["amount"],
        },
    },
    {
        "name": "agentnet_search_skills",
        "description": (
            "Search for AI agent skills on skills.sh (1.8M+ installs). "
            "Find reusable SKILL.md knowledge packages — workflows, best practices, "
            "templates. Install with: npx skills add <owner/repo@skill>"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search for (e.g. 'code review', 'testing', 'react')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-200)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_discover_skills",
        "description": (
            "AI-powered skill and plugin discovery across all sources. "
            "Describe your use case and get ranked results from skills.sh, "
            "SkillsMP, ClawHub, and Claude marketplace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {
                    "type": "string",
                    "description": "Describe what you need (e.g. 'set up CI/CD for React app')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10,
                },
            },
            "required": ["use_case"],
        },
    },
    {
        "name": "agentnet_search_skillsmp",
        "description": (
            "Search for AI agent skills on SkillsMP (skillsmp.com). "
            "Alternative skills index with category filtering and sort options."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search for",
                },
                "limit": {
                    "type": "integer",
                    "description": "Results per page (1-50)",
                    "default": 20,
                },
                "page": {
                    "type": "integer",
                    "description": "Page number",
                    "default": 1,
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["recent", "stars"],
                    "description": "Sort order",
                    "default": "recent",
                },
                "category": {
                    "type": "string",
                    "description": "Category slug filter (e.g. 'data-ai', 'development', 'testing-security')",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_search_claude_plugins",
        "description": (
            "Search the Claude Code plugin marketplace. "
            "Find plugins that extend Claude Code with new tools, skills, and integrations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search for (e.g. 'security', 'database', 'deployment')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-50)",
                    "default": 20,
                },
                "category": {
                    "type": "string",
                    "description": "Category filter: development, security, database, productivity, deployment, monitoring, design, location",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_search_clawhub",
        "description": (
            "Search ClawHub — the OpenClaw plugin marketplace with 52k+ tools. "
            "Find skills, code-plugins, and bundle-plugins for OpenClaw agents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search for (e.g. 'testing', 'deployment', 'security')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-100)",
                    "default": 20,
                },
                "category": {
                    "type": "string",
                    "description": "Category filter: mcp-tooling, data, security, observability, automation, deployment, dev-tools",
                },
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
