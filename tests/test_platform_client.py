import httpx
import pytest
from agentnet_cli.platform.client import PlatformClient, PlatformError, _validate_path_segment


@pytest.fixture()
def mock_transport():
    return httpx.MockTransport(lambda req: httpx.Response(200, json={"agents": []}))


@pytest.fixture()
def client(mock_transport):
    return PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=mock_transport),
    )


def _make_client(transport):
    """Helper to build a PlatformClient with a given MockTransport."""
    return PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    )


def test_discover(client):
    result = client.discover(query="translation")
    assert "agents" in result


def test_wallet_balance(mock_transport):
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"balance_minor": 1000, "currency": "INR"})
    )
    c = PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    )
    result = c.wallet_balance(agent_id="agent_123")
    assert result["balance_minor"] == 1000


def test_auth_header_sent():
    def check_auth(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer agn_test"
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(check_auth)
    c = PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    )
    c.discover(query="test")


# --- _handle_response error codes ---


def test_handle_response_401():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(401, json={"detail": "unauthorized"})
    )
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Authentication failed"):
        c.discover(query="test")


def test_handle_response_403():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(403, json={"detail": "forbidden"})
    )
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Authentication failed"):
        c.discover(query="test")


def test_handle_response_429():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(429, json={"detail": "too many requests"})
    )
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Rate limited"):
        c.discover(query="test")


def test_handle_response_500():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(500, json={"detail": "internal error"})
    )
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Platform server error"):
        c.discover(query="test")


def test_handle_response_other_error():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(418, json={"detail": "teapot"})
    )
    c = _make_client(transport)
    with pytest.raises(PlatformError, match=r"Request failed \(418\)"):
        c.discover(query="test")


def test_handle_response_invalid_json():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, content=b"<html>error</html>", headers={"content-type": "text/html"}
        )
    )
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Invalid response from platform"):
        c.discover(query="test")


# --- _validate_path_segment ---


def test_validate_path_segment_valid():
    _validate_path_segment("agt_abc123")  # should not raise


def test_validate_path_segment_traversal():
    with pytest.raises(PlatformError, match="Invalid identifier"):
        _validate_path_segment("../admin")


def test_validate_path_segment_slash():
    with pytest.raises(PlatformError, match="Invalid identifier"):
        _validate_path_segment("foo/bar")


def test_validate_path_segment_empty():
    with pytest.raises(PlatformError, match="Invalid identifier"):
        _validate_path_segment("")


# --- validation integration ---


def test_get_agent_validates_id():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Invalid identifier"):
        c.get_agent(agent_id="../admin")


def test_wallet_balance_validates_id():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    c = _make_client(transport)
    with pytest.raises(PlatformError, match="Invalid identifier"):
        c.wallet_balance(agent_id="foo/bar")


# --- context manager & close ---


def test_context_manager():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    with PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    ) as c:
        result = c.discover(query="test")
        assert result == {"ok": True}


def test_close_method():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    c = _make_client(transport)
    c.close()  # should not crash


# --- User-Agent header ---


def test_user_agent_header():
    def check_ua(req: httpx.Request) -> httpx.Response:
        assert "agentnet-cli/" in req.headers["user-agent"]
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(check_ua)
    c = _make_client(transport)
    c.discover(query="test")


# --- endpoint verification for use_agent, continue_session, settle_session, wallet_topup, discover_agents ---


def test_use_agent():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/agt_1/use"
        assert req.method == "POST"
        import json
        body = json.loads(req.content)
        assert body["message"] == "translate hello"
        assert body["amount"] == 5.0
        return httpx.Response(200, json={"session_id": "s1"})

    c = _make_client(httpx.MockTransport(handler))
    result = c.use_agent(agent_id="agt_1", task="translate hello", max_amount=5.0)
    assert result["session_id"] == "s1"


def test_continue_session():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/sessions/sess_abc/continue"
        assert req.method == "POST"
        return httpx.Response(200, json={"reply": "ok"})

    c = _make_client(httpx.MockTransport(handler))
    result = c.continue_session(session_id="sess_abc", message="hi")
    assert result["reply"] == "ok"


def test_settle_session():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/sessions/sess_abc/settle"
        assert req.method == "POST"
        return httpx.Response(200, json={"settled": True})

    c = _make_client(httpx.MockTransport(handler))
    result = c.settle_session(session_id="sess_abc")
    assert result["settled"] is True


def test_wallet_topup():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/wallet/agt_1/topup"
        assert req.method == "POST"
        import json
        body = json.loads(req.content)
        assert body["amount"] == 100.0
        return httpx.Response(200, json={"new_balance": 200})

    c = _make_client(httpx.MockTransport(handler))
    result = c.wallet_topup(agent_id="agt_1", amount=100.0)
    assert result["new_balance"] == 200


def test_discover_agents():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert "q=weather" in str(req.url)
        return httpx.Response(200, json={"agents": ["a1"]})

    c = _make_client(httpx.MockTransport(handler))
    result = c.discover_agents(query="weather", limit=10)
    assert result["agents"] == ["a1"]
