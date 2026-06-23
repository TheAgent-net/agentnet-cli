import httpx
import pytest

from agentnet_cli.tools.upstream_mcp import UpstreamMCP, UpstreamMCPError, _parse_sse


def _sse(body_json: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=f"event: message\ndata: {body_json}\n\n",
    )


def _client(transport: httpx.MockTransport, **kwargs) -> UpstreamMCP:
    return UpstreamMCP(url="https://upstream.test/mcp", http_client=httpx.Client(transport=transport), **kwargs)


# -- _parse_sse --


def test_parse_sse_standard_frame():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    assert _parse_sse(body) == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_parse_sse_ignores_comment_lines():
    body = ': keep-alive\nevent: message\ndata: {"id":2}\n\n'
    assert _parse_sse(body) == {"id": 2}


def test_parse_sse_multiline_data():
    body = 'event: message\ndata: {"a":1,\ndata: "b":2}\n\n'
    assert _parse_sse(body) == {"a": 1, "b": 2}


def test_parse_sse_no_data_raises():
    with pytest.raises(UpstreamMCPError, match="No data frame"):
        _parse_sse("event: ping\n\n")


def test_parse_sse_malformed_json_raises():
    with pytest.raises(UpstreamMCPError, match="Malformed SSE"):
        _parse_sse("data: {not json}\n\n")


# -- initialize: session capture + initialized notification --


def test_initialize_captures_session_and_sends_initialized():
    calls: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content)
        calls.append({"method": body.get("method"), "session": req.headers.get("mcp-session-id")})
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "mcp-session-id": "sess-123"},
                text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"exa"}}}\n\n',
            )
        return httpx.Response(202, text="")  # notification ack

    up = _client(httpx.MockTransport(handler))
    result = up.initialize({"protocolVersion": "2024-11-05", "capabilities": {}})

    assert result["result"]["serverInfo"]["name"] == "exa"
    assert up._session_id == "sess-123"
    # First call is initialize, second is notifications/initialized carrying the captured session.
    assert calls[0]["method"] == "initialize"
    assert calls[1]["method"] == "notifications/initialized"
    assert calls[1]["session"] == "sess-123"


def test_request_echoes_session_id():
    seen_sessions: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content)
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "mcp-session-id": "sess-xyz"},
                text='event: message\ndata: {"id":1,"result":{}}\n\n',
            )
        if body.get("method") == "tools/call":
            seen_sessions.append(req.headers.get("mcp-session-id"))
            return _sse('{"jsonrpc":"2.0","id":2,"result":{"content":[]}}')
        return httpx.Response(202, text="")

    up = _client(httpx.MockTransport(handler))
    up.initialize({"capabilities": {}})
    up.request("tools/call", {"name": "web_search_exa", "arguments": {}}, req_id=2)
    assert seen_sessions == ["sess-xyz"]


# -- JSON (non-SSE) content-type fallback --


def test_plain_json_response_supported():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 9, "result": {"tools": []}})

    up = _client(httpx.MockTransport(handler))
    env = up.request("tools/list", {}, req_id=9)
    assert env["result"]["tools"] == []


# -- session expiry: re-init once then retry --


def test_session_expiry_reinitializes_and_retries():
    state = {"served_409": False, "init_count": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content)
        method = body.get("method")
        if method == "initialize":
            state["init_count"] += 1
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "mcp-session-id": f"sess-{state['init_count']}"},
                text='event: message\ndata: {"id":1,"result":{}}\n\n',
            )
        if method == "tools/call":
            if not state["served_409"]:
                state["served_409"] = True
                return httpx.Response(409, text="session expired")
            return _sse('{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"ok"}]}}')
        return httpx.Response(202, text="")

    up = _client(httpx.MockTransport(handler))
    up.initialize({"capabilities": {}})
    env = up.request("tools/call", {"name": "web_search_exa", "arguments": {}}, req_id=3)

    assert env["result"]["content"][0]["text"] == "ok"
    assert state["init_count"] == 2  # initial + one re-init after the 409


def test_network_error_raises_upstream_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    up = _client(httpx.MockTransport(handler))
    with pytest.raises(UpstreamMCPError, match="Upstream request failed"):
        up.request("tools/list", {}, req_id=1)
