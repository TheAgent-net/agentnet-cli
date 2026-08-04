"""Tests for the MCP JSON-RPC server."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agentnet_cli.tools.mcp_server import (
    _error_response,
    _success_response,
    serve,
)
from agentnet_cli.tools.tool_defs import mcp_tool_specs


def _run_server(
    lines: list[str],
    *,
    token: str | None = "test_token",
    platform_url: str = "https://test.agentnet.market",
    action_side_effects: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    stdin_text = "\n".join(lines) + "\n" if lines else ""
    stdin = io.StringIO(stdin_text)
    stdout = io.StringIO()

    creds = None if not token else (token, platform_url)
    probe = MagicMock() if creds else None

    with (
        patch("agentnet_cli.tools.mcp_server.sys.stdin", stdin),
        patch("agentnet_cli.tools.mcp_server.sys.stdout", stdout),
        patch("agentnet_cli.tools.mcp_server.get_credentials", return_value=creds),
        patch("agentnet_cli.tools.mcp_server.make_platform_client", return_value=probe),
        patch("agentnet_cli.tools.mcp_server.start_detached_process"),
        patch("agentnet_cli.tools.mcp_server.ToolActions") as MockActions,
    ):
        mock_instance = MockActions.return_value
        mock_instance.search.return_value = {"query": "x", "type": "all", "results": []}
        if action_side_effects:
            for name, effect in action_side_effects.items():
                setattr(mock_instance, name, effect)
        serve()

    output = stdout.getvalue()
    if not output.strip():
        return []
    return [json.loads(line) for line in output.strip().split("\n") if line.strip()]


class TestErrorResponse:
    def test_structure(self):
        resp = _error_response(42, -32600, "Invalid Request")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "Invalid Request"


class TestSuccessResponse:
    def test_structure(self):
        resp = _success_response(1, {"hello": "world"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"] == {"hello": "world"}


class TestToolSpecs:
    def test_only_search(self):
        tools = mcp_tool_specs()
        assert [d["name"] for d in tools] == ["agentnet_search"]
        assert "inputSchema" in tools[0]


class TestServeBasics:
    def test_initialize(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        responses = _run_server([req])
        assert len(responses) == 1
        assert responses[0]["result"]["serverInfo"]["name"] == "agentnet"

    def test_tools_list(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        responses = _run_server([req])
        tools = responses[0]["result"]["tools"]
        assert {t["name"] for t in tools} == {"agentnet_search"}

    def test_tools_call_success(self):
        req = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "agentnet_search",
                    "arguments": {"query": "test"},
                },
            }
        )
        responses = _run_server([req])
        assert "result" in responses[0]
        content = responses[0]["result"]["content"][0]["text"]
        assert json.loads(content)["results"] == []

    def test_tools_call_handler_error_is_tool_error(self):
        mock = MagicMock()
        mock.side_effect = RuntimeError("upstream down")
        req = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "agentnet_search",
                    "arguments": {"query": "test"},
                },
            }
        )
        responses = _run_server(
            [req],
            action_side_effects={"search": mock},
        )
        assert responses[0]["result"]["isError"] is True
        assert "upstream down" in responses[0]["result"]["content"][0]["text"]

    def test_parse_error(self):
        responses = _run_server(
            ["{invalid", json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})]
        )
        assert responses[0]["error"]["code"] == -32700
        assert responses[1]["id"] == 10

    def test_unknown_method(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 14, "method": "unknown/thing"})
        responses = _run_server([req])
        assert responses[0]["error"]["code"] == -32601
        assert "Method not found" in responses[0]["error"]["message"]

    def test_notification_no_response(self):
        req = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert _run_server([req]) == []

    def test_empty_stdin_closes_actions(self):
        stdin = io.StringIO("")
        stdout = io.StringIO()
        with (
            patch("agentnet_cli.tools.mcp_server.sys.stdin", stdin),
            patch("agentnet_cli.tools.mcp_server.sys.stdout", stdout),
            patch(
                "agentnet_cli.tools.mcp_server.get_credentials",
                return_value=("tok", "https://test"),
            ),
            patch("agentnet_cli.tools.mcp_server.make_platform_client", return_value=MagicMock()),
            patch("agentnet_cli.tools.mcp_server.start_detached_process"),
            patch("agentnet_cli.tools.mcp_server.ToolActions") as MockActions,
        ):
            serve()
        MockActions.return_value.close.assert_called_once()


class TestNoTokenConfigured:
    def test_sys_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _run_server([], token=None)
        assert exc_info.value.code == 1
