from __future__ import annotations

import json
import os
import sys
from typing import Any

from .. import __version__
from ..config import load_config
from .tools import ToolHandlers

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "agentnet_discover",
        "description": "Search the Agent-net marketplace for products and services. Use this when the user needs anything — weather, translation, code review, food, design, etc. Returns listings with prices.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you're looking for (e.g. 'weather forecast', 'logo design', 'code review')"},
                "category": {"type": "string", "description": "Filter by category"},
                "max_results": {"type": "integer", "description": "Max results to return", "default": 20},
                "max_price": {"type": "integer", "description": "Max price filter in USD"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_discover_agents",
        "description": "Search for AI agents on the marketplace by name or capability",
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
        "description": "Get full details about an agent — skills, pricing, trust score. Call this after discover to learn more before hiring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID from discovery results"},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "agentnet_use_agent",
        "description": "Hire an agent to do a task. Sends the task, pays, and returns the result. For simple tasks, completes and settles in one call. For complex tasks, returns a session_id for follow-up via continue_session. IMPORTANT: amount is in USD (e.g. 3.0 = $3.00). Always confirm price with user before calling.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent to hire (from discover results)"},
                "task": {"type": "string", "description": "Detailed task description — include all context the agent needs (location, preferences, etc.)"},
                "max_amount": {"type": "number", "description": "Budget in USD (e.g. 1.5 for $1.50, max 100). Use the listing price from discover results.", "default": 0},
            },
            "required": ["agent_id", "task"],
        },
    },
    {
        "name": "agentnet_continue_session",
        "description": "Send a follow-up message in a multi-turn session. Only needed when use_agent returned status 'escrowed' (not 'settled').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID from the use_agent response"},
                "message": {"type": "string", "description": "Follow-up message or additional instructions"},
            },
            "required": ["session_id", "message"],
        },
    },
    {
        "name": "agentnet_settle_session",
        "description": "Confirm satisfaction and release payment for a multi-turn session. Only needed when use_agent returned status 'escrowed'. Do NOT call if status was already 'settled'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to settle"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "agentnet_wallet",
        "description": "Check your Agent-net wallet balance or view transaction history",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["balance", "history"], "description": "'balance' for current balance, 'history' for recent transactions"},
                "limit": {"type": "integer", "description": "Number of history entries to return", "default": 50},
            },
            "required": ["action"],
        },
    },
    {
        "name": "agentnet_wallet_topup",
        "description": "Add funds to your Agent-net wallet",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount to add in USD"},
            },
            "required": ["amount"],
        },
    },
]


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
        "agentnet_get_agent": lambda p: handlers.get_agent(**p),
        "agentnet_use_agent": lambda p: handlers.use_agent(**p),
        "agentnet_continue_session": lambda p: handlers.continue_session(**p),
        "agentnet_settle_session": lambda p: handlers.settle_session(**p),
        "agentnet_wallet": lambda p: handlers.wallet(**p),
        "agentnet_wallet_topup": lambda p: handlers.wallet_topup(**p),
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
                    _write_response(_success_response(req_id, {"tools": TOOL_DEFINITIONS}))
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
