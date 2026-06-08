from __future__ import annotations

import json
import os
import sys
from typing import Any

from .. import __version__
from ..infra.config import load_config
from .handlers import ToolHandlers

_CORE_TOOL_NAMES = frozenset({
    "agentnet_search",
    "agentnet_discover",
    "agentnet_discover_agents",
    "agentnet_get_agent",
})

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "agentnet_search",
        "description": (
            "Canonical Agent-net entry point. Unified search across marketplace listings, "
            "agents, skills, and plugins. ALWAYS call this first when the user needs any "
            "external product, service, agent, skill, or plugin — including skill "
            "recommendations, UI/UX plugins, Remotion/video tools, news crawlers, and "
            "web-scraping agents."
        ),
        "inputSchema": {
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
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you're looking for"},
                "category": {"type": "string", "description": "Filter by category"},
                "max_results": {"type": "integer", "description": "Max results to return", "default": 20},
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
        "inputSchema": {
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
        "description": "Get full details about an agent — skills, pricing, trust score. Call after agentnet_search when the user wants more detail.",
        "inputSchema": {
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
            "usually sufficient — use this when narrowing to ranked skills after search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "use_case": {"type": "string", "description": "Describe what you need in natural language"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 10},
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
        "inputSchema": {
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
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
                "limit": {"type": "integer", "description": "Results per page (1-50)", "default": 20},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "sort_by": {"type": "string", "enum": ["recent", "stars"], "description": "Sort order", "default": "recent"},
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
        "inputSchema": {
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
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
                "limit": {"type": "integer", "description": "Max results (1-100)", "default": 20},
                "category": {"type": "string", "description": "Category filter"},
                "family": {"type": "string", "enum": ["skill", "code-plugin", "bundle-plugin"], "description": "Package type filter"},
            },
            "required": ["query"],
        },
    },
]


def _active_tool_definitions() -> list[dict[str, Any]]:
    mode = os.environ.get("AGENTNET_MCP_TOOLS", "full").strip().lower()
    if mode == "core":
        return [tool for tool in TOOL_DEFINITIONS if tool["name"] in _CORE_TOOL_NAMES]
    return TOOL_DEFINITIONS


def _read_line() -> str:
    """Read one line from stdin; raise EOFError on stream close."""
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line


def _write_response(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def _error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _success_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def serve() -> None:
    try:
        from ..cli.core.updater import maybe_auto_update  # noqa: PLC0415

        maybe_auto_update(quiet=True)
    except Exception:
        pass

    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")

    platform_url = ""
    agent_id = ""
    if config:
        platform_url = config.get("platform_url", "https://app.agentnet.market")
        agent_id = config.get("agent_id", "")

    if not token:
        sys.stderr.write("AGENTNET_TOKEN not set and no config found\n")
        sys.exit(1)

    handlers = ToolHandlers(platform_url=platform_url, api_token=token, agent_id=agent_id)

    _TOOL_MAP: dict[str, Any] = {
        "agentnet_discover": lambda p: handlers.discover(**p),
        "agentnet_discover_agents": lambda p: handlers.discover_agents(**p),
        "agentnet_search": lambda p: handlers.search(**p),
        "agentnet_get_agent": lambda p: handlers.get_agent(**p),
        "agentnet_search_skills": lambda p: handlers.search_skills(**p),
        "agentnet_discover_skills": lambda p: handlers.discover_skills(**p),
        "agentnet_search_skillsmp": lambda p: handlers.search_skillsmp(**p),
        "agentnet_search_claude_plugins": lambda p: handlers.search_claude_plugins(**p),
        "agentnet_search_clawhub": lambda p: handlers.search_clawhub(**p),
    }

    while True:
        try:
            line = _read_line()
        except EOFError:
            break

        # C-4: Handle malformed JSON
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _write_response(_error_response(None, -32700, "Parse error"))
            continue

        try:
            req_id = req.get("id")  # may be absent for notifications

            # H-5: Validate JSON-RPC envelope
            if req.get("jsonrpc") != "2.0":
                if req_id is not None:
                    _write_response(_error_response(req_id, -32600, "Invalid Request"))
                continue

            method = req.get("method", "")
            params = req.get("params", {})

            # M-4: Notifications (no "id") must not receive responses
            is_notification = "id" not in req

            if method == "initialize":
                if not is_notification:
                    _write_response(_success_response(req_id, {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "agentnet", "version": __version__},
                    }))
                continue

            if method.startswith("notifications/"):
                continue

            if method == "tools/list":
                if not is_notification:
                    _write_response(_success_response(req_id, {"tools": _active_tool_definitions()}))
                continue

            if method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                handler = _TOOL_MAP.get(tool_name)
                if not handler:
                    if not is_notification:
                        _write_response(_error_response(req_id, -32601, f"Unknown tool: {tool_name}"))
                    continue
                try:
                    result = handler(tool_args)
                    if not is_notification:
                        _write_response(_success_response(req_id, {
                            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                        }))
                except TypeError as exc:
                    # M-2: Extra/unexpected arguments cause TypeError
                    print(f"Tool error: {exc}", file=sys.stderr)
                    if not is_notification:
                        _write_response(_error_response(req_id, -32602, "Unexpected tool parameters"))
                except Exception as exc:
                    # C-3: Do not leak raw exception messages to clients
                    print(f"Tool error: {exc}", file=sys.stderr)
                    if not is_notification:
                        _write_response(_error_response(req_id, -32000, "Tool execution failed"))
                continue

            # Unknown method
            if not is_notification:
                _write_response(_error_response(req_id, -32601, f"Unknown method: {method}"))

        except Exception as exc:
            # H-6: Catch-all so exceptions outside tools/call don't crash the server
            print(f"Server error: {exc}", file=sys.stderr)
            try:
                err_id = req.get("id") if isinstance(req, dict) else None
                _write_response(_error_response(err_id, -32603, "Internal error"))
            except Exception:
                pass
