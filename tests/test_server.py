"""Tests for the MCP JSON-RPC server (src/agentnet_cli/mcp/server.py)."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

import pytest

from agentnet_cli.mcp.server import (
    TOOL_DEFINITIONS,
    _error_response,
    _success_response,
    serve,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_server(
    lines: list[str],
    config: dict[str, Any] | None = None,
    token: str = "test_token",
    env_token: str | None = None,
) -> list[dict[str, Any]]:
    """Feed *lines* into ``serve()`` via mocked stdin; return parsed JSON responses.

    Parameters
    ----------
    lines:
        Raw strings (each becomes one stdin line).
    config:
        Value returned by ``load_config()``.  ``None`` uses a sensible default.
    token:
        Shortcut — sets ``api_token`` in the default config.
    env_token:
        If provided, placed in the mocked ``AGENTNET_TOKEN`` env-var.
        If ``None``, the env-var is **absent** (forcing the server to fall back
        to config).
    """

    stdin_text = "\n".join(lines) + "\n" if lines else ""
    stdin = io.StringIO(stdin_text)
    stdout = io.StringIO()

    mock_config = config if config is not None else {
        "api_token": token,
        "platform_url": "https://test.agentnet.market",
        "agent_id": "agent_test_1",
    }

    # Build environment dict — only include AGENTNET_TOKEN when explicitly supplied
    env: dict[str, str] = {}
    if env_token is not None:
        env["AGENTNET_TOKEN"] = env_token

    with (
        patch("agentnet_cli.mcp.server.sys.stdin", stdin),
        patch("agentnet_cli.mcp.server.sys.stdout", stdout),
        patch("agentnet_cli.mcp.server.load_config", return_value=mock_config),
        patch("agentnet_cli.mcp.server.os.environ", env),
        patch("agentnet_cli.mcp.server.ToolHandlers") as MockHandlers,
    ):
        mock_instance = MockHandlers.return_value

        # Wire up all handler methods with safe defaults
        mock_instance.discover.return_value = {"results": [], "total": 0}
        mock_instance.discover_agents.return_value = {"agents": [], "total": 0}
        mock_instance.get_agent.return_value = {"agent_id": "ag_1", "name": "TestBot"}
        mock_instance.use_agent.return_value = {"status": "settled", "result": "done"}
        mock_instance.continue_session.return_value = {"status": "escrowed"}
        mock_instance.settle_session.return_value = {"status": "settled"}
        mock_instance.wallet.return_value = {"balance_minor": 1000}
        mock_instance.wallet_topup.return_value = {"ok": True}

        serve()

    output = stdout.getvalue()
    if not output.strip():
        return []
    return [json.loads(line) for line in output.strip().split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# 1–3: Infrastructure helpers
# ---------------------------------------------------------------------------


class TestErrorResponse:
    """1. ``_error_response`` returns a correct JSON-RPC error envelope."""

    def test_structure(self):
        resp = _error_response(42, -32600, "Invalid Request")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "Invalid Request"

    def test_null_id(self):
        resp = _error_response(None, -32700, "Parse error")
        assert resp["id"] is None

    def test_string_id(self):
        resp = _error_response("abc", -32601, "Method not found")
        assert resp["id"] == "abc"


class TestSuccessResponse:
    """2. ``_success_response`` returns a correct JSON-RPC success envelope."""

    def test_structure(self):
        resp = _success_response(1, {"hello": "world"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"] == {"hello": "world"}

    def test_null_result(self):
        resp = _success_response(5, None)
        assert resp["result"] is None


class TestToolDefinitions:
    """3. ``TOOL_DEFINITIONS`` is non-empty; each entry has required keys."""

    def test_non_empty(self):
        assert len(TOOL_DEFINITIONS) > 0

    def test_required_keys(self):
        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Missing 'name' in {defn}"
            assert "description" in defn, f"Missing 'description' in {defn}"
            assert "inputSchema" in defn, f"Missing 'inputSchema' in {defn}"

    def test_all_eight_tools_present(self):
        names = {d["name"] for d in TOOL_DEFINITIONS}
        expected = {
            "agentnet_discover",
            "agentnet_discover_agents",
            "agentnet_get_agent",
            "agentnet_use_agent",
            "agentnet_continue_session",
            "agentnet_settle_session",
            "agentnet_wallet",
            "agentnet_wallet_topup",
        }
        assert names == expected

    def test_input_schema_is_object(self):
        for defn in TOOL_DEFINITIONS:
            schema = defn["inputSchema"]
            assert schema.get("type") == "object"
            assert "properties" in schema


# ---------------------------------------------------------------------------
# 4–15: ``serve()`` function
# ---------------------------------------------------------------------------


class TestInitialize:
    """4. ``initialize`` method returns protocol info."""

    def test_basic(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        responses = _run_server([req])
        assert len(responses) == 1
        r = responses[0]
        assert r["id"] == 1
        assert "protocolVersion" in r["result"]
        assert "capabilities" in r["result"]
        info = r["result"]["serverInfo"]
        assert info["name"] == "agentnet"
        assert "version" in info


class TestToolsList:
    """5. ``tools/list`` returns all 8 tool definitions."""

    def test_tools_list(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        responses = _run_server([req])
        assert len(responses) == 1
        tools = responses[0]["result"]["tools"]
        assert len(tools) == 8
        names = {t["name"] for t in tools}
        assert "agentnet_discover" in names
        assert "agentnet_wallet" in names


class TestToolsCallValid:
    """6. ``tools/call`` with a valid tool returns handler result."""

    def test_discover(self):
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "agentnet_discover", "arguments": {"query": "weather"}},
        })
        responses = _run_server([req])
        assert len(responses) == 1
        r = responses[0]
        assert r["id"] == 3
        assert "result" in r
        content = r["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        payload = json.loads(content[0]["text"])
        assert payload == {"results": [], "total": 0}


class TestToolsCallUnknown:
    """7. ``tools/call`` with unknown tool returns -32601."""

    def test_unknown_tool(self):
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        responses = _run_server([req])
        assert len(responses) == 1
        err = responses[0]["error"]
        assert err["code"] == -32601
        assert "Unknown tool" in err["message"]


class TestToolsCallRaises:
    """8. Handler raising generic ``Exception`` returns -32000."""

    def test_tool_execution_failed(self):
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "agentnet_discover", "arguments": {"query": "test"}},
        })

        stdin = io.StringIO(req + "\n")
        stdout = io.StringIO()
        env = {"AGENTNET_TOKEN": "tok"}
        mock_config = {
            "api_token": "tok",
            "platform_url": "https://test",
            "agent_id": "ag_1",
        }

        with (
            patch("agentnet_cli.mcp.server.sys.stdin", stdin),
            patch("agentnet_cli.mcp.server.sys.stdout", stdout),
            patch("agentnet_cli.mcp.server.load_config", return_value=mock_config),
            patch("agentnet_cli.mcp.server.os.environ", env),
            patch("agentnet_cli.mcp.server.ToolHandlers") as MockHandlers,
        ):
            mock_instance = MockHandlers.return_value
            mock_instance.discover.side_effect = RuntimeError("upstream down")
            serve()

        responses = [json.loads(line) for line in stdout.getvalue().strip().split("\n") if line.strip()]
        assert len(responses) == 1
        err = responses[0]["error"]
        assert err["code"] == -32000
        assert err["message"] == "Tool execution failed"
        # Raw exception message must NOT leak:
        assert "upstream down" not in json.dumps(responses[0])


class TestToolsCallTypeError:
    """9. Handler raising ``TypeError`` (bad params) returns -32602."""

    def test_unexpected_params(self):
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "agentnet_discover", "arguments": {"query": "x"}},
        })

        stdin = io.StringIO(req + "\n")
        stdout = io.StringIO()
        env = {"AGENTNET_TOKEN": "tok"}
        mock_config = {
            "api_token": "tok",
            "platform_url": "https://test",
            "agent_id": "ag_1",
        }

        with (
            patch("agentnet_cli.mcp.server.sys.stdin", stdin),
            patch("agentnet_cli.mcp.server.sys.stdout", stdout),
            patch("agentnet_cli.mcp.server.load_config", return_value=mock_config),
            patch("agentnet_cli.mcp.server.os.environ", env),
            patch("agentnet_cli.mcp.server.ToolHandlers") as MockHandlers,
        ):
            mock_instance = MockHandlers.return_value
            mock_instance.discover.side_effect = TypeError("unexpected keyword argument 'bad'")
            serve()

        responses = [json.loads(line) for line in stdout.getvalue().strip().split("\n") if line.strip()]
        assert len(responses) == 1
        err = responses[0]["error"]
        assert err["code"] == -32602
        assert err["message"] == "Unexpected tool parameters"


class TestParseError:
    """10. Malformed JSON yields -32700 and the server continues."""

    def test_malformed_then_valid(self):
        bad_line = "{invalid json!!"
        good_line = json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
        responses = _run_server([bad_line, good_line])
        assert len(responses) == 2
        # First: parse error
        assert responses[0]["error"]["code"] == -32700
        assert responses[0]["id"] is None
        # Second: valid tools/list
        assert "result" in responses[1]
        assert responses[1]["id"] == 10


class TestInvalidRequest:
    """11. Missing ``jsonrpc`` field returns -32600."""

    def test_no_jsonrpc_field(self):
        req = json.dumps({"id": 1, "method": "test"})
        responses = _run_server([req])
        assert len(responses) == 1
        err = responses[0]["error"]
        assert err["code"] == -32600
        assert err["message"] == "Invalid Request"


class TestNotificationNoResponse:
    """12. Notifications (no ``id``) must not produce a response."""

    def test_notification_ignored(self):
        req = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        responses = _run_server([req])
        assert responses == []


class TestToolsCallNotification:
    """13. ``tools/call`` as notification (no id) produces no response even on success."""

    def test_no_response(self):
        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "agentnet_discover", "arguments": {"query": "test"}},
        })
        responses = _run_server([req])
        assert responses == []


class TestUnknownMethod:
    """14. Unknown method returns -32601."""

    def test_unknown_method(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 14, "method": "unknown/thing"})
        responses = _run_server([req])
        assert len(responses) == 1
        err = responses[0]["error"]
        assert err["code"] == -32601
        assert "Unknown method" in err["message"]


class TestEOFHandling:
    """15. Empty stdin causes ``serve()`` to exit cleanly."""

    def test_empty_stdin(self):
        responses = _run_server([])
        assert responses == []


class TestNoTokenConfigured:
    """16. No token anywhere causes ``sys.exit(1)``."""

    def test_sys_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _run_server([], config={"platform_url": "https://test", "agent_id": "ag_1"}, token="")
        assert exc_info.value.code == 1

    def test_none_config_no_env(self):
        """Neither env-var nor config file provides a token."""
        with pytest.raises(SystemExit) as exc_info:
            _run_server([], config=None, token="")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Additional edge-case / integration tests
# ---------------------------------------------------------------------------


class TestMultipleRequests:
    """Multiple sequential requests in one session."""

    def test_init_then_list_then_call(self):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "agentnet_wallet", "arguments": {"action": "balance"}},
            }),
        ]
        responses = _run_server(lines)
        assert len(responses) == 3
        assert "protocolVersion" in responses[0]["result"]
        assert len(responses[1]["result"]["tools"]) == 8
        content_text = json.loads(responses[2]["result"]["content"][0]["text"])
        assert content_text == {"balance_minor": 1000}


class TestTokenFromEnvOnly:
    """Server picks up AGENTNET_TOKEN even when config has no api_token."""

    def test_env_token_used(self):
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        responses = _run_server(
            [req],
            config={"platform_url": "https://test", "agent_id": "ag_1"},
            token="",
            env_token="env_tok_123",
        )
        assert len(responses) == 1
        assert "result" in responses[0]


class TestInitializeNotification:
    """Initialize sent as notification (no id) should produce no response."""

    def test_no_response(self):
        req = json.dumps({"jsonrpc": "2.0", "method": "initialize"})
        responses = _run_server([req])
        assert responses == []


class TestToolsListNotification:
    """tools/list sent as notification should produce no response."""

    def test_no_response(self):
        req = json.dumps({"jsonrpc": "2.0", "method": "tools/list"})
        responses = _run_server([req])
        assert responses == []


class TestInvalidRequestWithoutId:
    """Invalid request (no jsonrpc) without id should produce no response."""

    def test_no_response(self):
        req = json.dumps({"method": "test"})
        responses = _run_server([req])
        assert responses == []


class TestAllToolHandlers:
    """Verify all 8 tools can be invoked successfully through serve()."""

    @pytest.mark.parametrize(
        "tool_name,arguments",
        [
            ("agentnet_discover", {"query": "test"}),
            ("agentnet_discover_agents", {"query": "bot"}),
            ("agentnet_get_agent", {"agent_id": "ag_1"}),
            ("agentnet_use_agent", {"agent_id": "ag_1", "task": "do stuff"}),
            ("agentnet_continue_session", {"session_id": "s1", "message": "more"}),
            ("agentnet_settle_session", {"session_id": "s1"}),
            ("agentnet_wallet", {"action": "balance"}),
            ("agentnet_wallet_topup", {"amount": 10.0}),
        ],
    )
    def test_each_tool(self, tool_name: str, arguments: dict[str, Any]):
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        responses = _run_server([req])
        assert len(responses) == 1
        assert "result" in responses[0]
        assert responses[0]["result"]["content"][0]["type"] == "text"
