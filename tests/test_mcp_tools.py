import json

import httpx
import pytest
from agentnet_cli.mcp.tools import ToolHandlers


@pytest.fixture()
def handlers():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"results": [], "total": 0}))
    client = httpx.Client(transport=transport)
    return ToolHandlers(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        agent_id="agent_123",
        http_client=client,
    )


def _make_handlers(handler_fn, agent_id="agent_123"):
    """Helper to build ToolHandlers with a custom MockTransport handler."""
    transport = httpx.MockTransport(handler_fn)
    return ToolHandlers(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        agent_id=agent_id,
        http_client=httpx.Client(transport=transport),
    )


def test_discover(handlers):
    result = handlers.discover(query="translation")
    assert isinstance(result, dict)


def test_wallet(handlers):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"balance_minor": 500}))
    h = ToolHandlers(
        platform_url="https://x", api_token="t", agent_id="ag_1",
        http_client=httpx.Client(transport=transport),
    )
    result = h.wallet(action="balance")
    assert result["balance_minor"] == 500


def test_discover_with_category(handlers):
    result = handlers.discover(query="test", category="translation")
    assert isinstance(result, dict)


# --- get_agent ---


def test_get_agent():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/agt_42"
        return httpx.Response(200, json={"agent_id": "agt_42", "name": "TestBot"})

    h = _make_handlers(handler)
    result = h.get_agent(agent_id="agt_42")
    assert result["agent_id"] == "agt_42"


# --- use_agent ---


def test_use_agent():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/agt_1/use"
        body = json.loads(req.content)
        assert body["message"] == "do something"
        assert body["amount"] == 10.0
        return httpx.Response(200, json={"session_id": "s1"})

    h = _make_handlers(handler)
    result = h.use_agent(agent_id="agt_1", task="do something", max_amount=10.0)
    assert result["session_id"] == "s1"


def test_use_agent_max_amount_validation_negative():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="max_amount must be between 0 and 1000"):
        h.use_agent(agent_id="agt_1", task="test", max_amount=-1)


def test_use_agent_max_amount_validation_too_high():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="max_amount must be between 0 and 1000"):
        h.use_agent(agent_id="agt_1", task="test", max_amount=1001)


def test_use_agent_max_amount_valid():
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert body["amount"] == 50.0
        return httpx.Response(200, json={"session_id": "s2"})

    h = _make_handlers(handler)
    result = h.use_agent(agent_id="agt_1", task="test", max_amount=50.0)
    assert result["session_id"] == "s2"


# --- continue_session ---


def test_continue_session():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/sessions/sess_1/continue"
        body = json.loads(req.content)
        assert body["message"] == "follow up"
        return httpx.Response(200, json={"reply": "noted"})

    h = _make_handlers(handler)
    result = h.continue_session(session_id="sess_1", message="follow up")
    assert result["reply"] == "noted"


# --- settle_session ---


def test_settle_session():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agents/sessions/sess_2/settle"
        return httpx.Response(200, json={"settled": True})

    h = _make_handlers(handler)
    result = h.settle_session(session_id="sess_2")
    assert result["settled"] is True


# --- wallet history ---


def test_wallet_history():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "/wallet/agent_123/history" in req.url.path
        return httpx.Response(200, json={"transactions": [{"id": "tx_1"}]})

    h = _make_handlers(handler)
    result = h.wallet(action="history")
    assert result["transactions"][0]["id"] == "tx_1"


# --- wallet invalid action ---


def test_wallet_invalid_action():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="Invalid action"):
        h.wallet(action="delete")


# --- wallet_topup ---


def test_wallet_topup():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "/wallet/agent_123/topup" in req.url.path
        body = json.loads(req.content)
        assert body["amount"] == 25.0
        return httpx.Response(200, json={"new_balance": 125})

    h = _make_handlers(handler)
    result = h.wallet_topup(amount=25.0)
    assert result["new_balance"] == 125


def test_wallet_topup_validation_zero():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="amount must be between 0"):
        h.wallet_topup(amount=0)


def test_wallet_topup_validation_negative():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="amount must be between 0"):
        h.wallet_topup(amount=-5)


def test_wallet_topup_validation_too_high():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="amount must be between 0"):
        h.wallet_topup(amount=10001)


# --- discover_agents ---


def test_discover_agents():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert "q=weather" in str(req.url)
        return httpx.Response(200, json={"agents": ["a1", "a2"]})

    h = _make_handlers(handler)
    result = h.discover_agents(query="weather", limit=10)
    assert result["agents"] == ["a1", "a2"]
