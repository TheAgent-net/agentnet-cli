"""Stdio JSON-RPC MCP server for Agent-net tools."""

from __future__ import annotations

import json
import sys
from typing import Any

from .. import __version__
from ..infra.credentials import get_credentials, make_platform_client
from ..infra.proc import agentnet_invocation, start_detached_process
from .handlers import ToolActions
from .tool_defs import TOOL_ACTIONS, mcp_tool_specs


def _read_line() -> str:
    """Read one line from stdin. Raise ``EOFError`` when the stream ends."""
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line


def _write_response(data: dict[str, Any]) -> None:
    """Write one JSON-RPC response line to stdout."""
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def _error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _success_response(req_id: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _start_background_update() -> None:
    """Start auto-update in the background. Do not wait."""
    try:
        start_detached_process([*agentnet_invocation(), "update", "--quiet", "--background"])
    except Exception:
        pass


def serve() -> None:
    """Run the MCP stdio server until stdin closes."""
    _start_background_update()

    creds = get_credentials()
    if creds is None:
        sys.stderr.write("AGENTNET_TOKEN not set and no config found\n")
        sys.exit(1)
    token, platform_url = creds

    probe = make_platform_client()
    if probe is None:
        sys.stderr.write("AGENTNET_TOKEN not set and no config found\n")
        sys.exit(1)
    probe.close()

    actions = ToolActions(platform_url=platform_url, api_token=token)
    tools = mcp_tool_specs()

    def _run_tool(name: str, params: dict[str, Any]) -> Any:
        method = TOOL_ACTIONS.get(name)
        if not method:
            raise KeyError(name)
        return getattr(actions, method)(**params)

    while True:
        try:
            line = _read_line()
        except EOFError:
            break

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _write_response(_error_response(None, -32700, "Parse error"))
            continue

        try:
            req_id = req.get("id")
            method = req.get("method", "")
            params = req.get("params") or {}

            if method == "initialize":
                _write_response(
                    _success_response(
                        req_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "agentnet", "version": __version__},
                        },
                    )
                )
                continue

            if method == "notifications/initialized":
                continue

            if method == "tools/list":
                _write_response(_success_response(req_id, {"tools": tools}))
                continue

            if method == "tools/call":
                name = params.get("name", "")
                args = params.get("arguments") or {}
                try:
                    result = _run_tool(name, args)
                    _write_response(
                        _success_response(
                            req_id,
                            {
                                "content": [
                                    {"type": "text", "text": json.dumps(result, indent=2)}
                                ],
                            },
                        )
                    )
                except Exception as e:
                    _write_response(
                        _success_response(
                            req_id,
                            {
                                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                                "isError": True,
                            },
                        )
                    )
                continue

            if req_id is not None:
                _write_response(_error_response(req_id, -32601, f"Method not found: {method}"))
        except Exception as e:
            _write_response(_error_response(req.get("id"), -32603, str(e)))

    actions.close()
