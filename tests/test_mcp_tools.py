import json
from unittest.mock import MagicMock

import httpx
import pytest
from agentnet_cli.tools.handlers import ToolHandlers


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


def test_handlers_context_manager_closes_owned_clients():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    platform_http = httpx.Client(transport=transport)
    skills_http = httpx.Client(transport=transport)
    skillsmp_http = httpx.Client(transport=transport)
    claude_http = httpx.Client(transport=transport)
    clawhub_http = httpx.Client(transport=transport)

    with ToolHandlers(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        agent_id="agent_123",
        http_client=platform_http,
        skills_http_client=skills_http,
        skillsmp_http_client=skillsmp_http,
        claude_marketplace_http_client=claude_http,
        clawhub_http_client=clawhub_http,
    ) as handlers:
        assert isinstance(handlers, ToolHandlers)

    assert platform_http.is_closed
    assert skills_http.is_closed
    assert skillsmp_http.is_closed
    assert claude_http.is_closed
    assert clawhub_http.is_closed


def test_discover(handlers):
    result = handlers.discover(query="translation")
    assert isinstance(result, dict)


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


# --- discover_agents ---


def test_discover_agents():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert "q=weather" in str(req.url)
        return httpx.Response(200, json={"agents": ["a1", "a2"]})

    h = _make_handlers(handler)
    result = h.discover_agents(query="weather", limit=10)
    assert result["agents"] == ["a1", "a2"]


# --- unified search ---


def test_search_unified_platform():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/search"
        assert req.url.params["q"] == "weather"
        assert req.url.params["type"] == "all"
        assert req.url.params["limit"] == "5"
        return httpx.Response(200, json={"query": "weather", "sources": ["agents"]})

    h = _make_handlers(handler)
    result = h.search(query="weather", limit=5)
    assert result["query"] == "weather"


# --- search_skills ---


def test_search_skills():
    payload = {"skills": [{"id": "org/repo/testing", "name": "testing", "installs": 100}], "count": 1}

    def skills_handler(req: httpx.Request) -> httpx.Response:
        assert "/api/search" in req.url.path
        assert req.url.params["q"] == "testing"
        return httpx.Response(200, json=payload)

    skills_http = httpx.Client(transport=httpx.MockTransport(skills_handler))
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    h._skills_client = __import__(
        "agentnet_cli.marketplace.skills.client", fromlist=["SkillsClient"]
    ).SkillsClient(http_client=skills_http)

    result = h.search_skills(query="testing")
    assert result["skills"][0]["name"] == "testing"


def test_search_skills_defaults():
    calls: list[httpx.Request] = []

    def skills_handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json={"skills": [], "count": 0})

    skills_http = httpx.Client(transport=httpx.MockTransport(skills_handler))
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    h._skills_client = __import__(
        "agentnet_cli.marketplace.skills.client", fromlist=["SkillsClient"]
    ).SkillsClient(http_client=skills_http)

    h.search_skills(query="debug")
    url = calls[0].url
    assert url.params["q"] == "debug"
    assert url.params["limit"] == "20"


# --- discover_skills ---


def test_discover_skills():
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    h._discovery = MagicMock()
    h._discovery.discover.return_value = {
        "use_case": "react testing",
        "results": [{"name": "react-test"}],
    }

    result = h.discover_skills(use_case="react testing", limit=3)

    h._discovery.discover.assert_called_once_with(use_case="react testing", limit=3)
    assert result["results"][0]["name"] == "react-test"


# --- search_skillsmp ---


def test_search_skillsmp():
    payload = {"data": [{"id": "s1", "name": "testing"}]}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/skills/skillsmp/search")
        assert req.url.params["q"] == "testing"
        assert req.url.params["sortBy"] == "stars"
        assert req.headers.get("authorization") == "Bearer agn_test"
        return httpx.Response(200, json=payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    h = ToolHandlers(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        agent_id="agent_123",
        http_client=http,
        skillsmp_http_client=http,
    )

    result = h.search_skillsmp(query="testing", sort_by="stars")
    assert result["data"][0]["name"] == "testing"


# --- search_claude_plugins ---


def test_search_claude_plugins():
    catalog = {
        "plugins": [
            {
                "name": "sql-helper",
                "description": "SQL query builder",
                "category": "database",
                "author": {"name": "ACME"},
            }
        ]
    }

    def catalog_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=catalog)

    claude_http = httpx.Client(transport=httpx.MockTransport(catalog_handler))
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    h._claude_marketplace = __import__(
        "agentnet_cli.marketplace.catalogs.claude_marketplace", fromlist=["ClaudeMarketplaceClient"]
    ).ClaudeMarketplaceClient(http_client=claude_http)

    result = h.search_claude_plugins(query="sql")
    assert result["total"] == 1
    assert result["results"][0]["name"] == "sql-helper"


# --- search_clawhub ---


def test_search_clawhub():
    payload = {"results": [{"score": 3.0, "slug": "qa-testing", "displayName": "QA Testing"}]}

    def clawhub_handler(req: httpx.Request) -> httpx.Response:
        assert "/api/v1/search" in req.url.path
        assert req.url.params["q"] == "testing"
        return httpx.Response(200, json=payload)

    clawhub_http = httpx.Client(transport=httpx.MockTransport(clawhub_handler))
    h = _make_handlers(lambda req: httpx.Response(200, json={}))
    h._clawhub_client = __import__(
        "agentnet_cli.marketplace.catalogs.clawhub", fromlist=["ClawHubClient"]
    ).ClawHubClient(http_client=clawhub_http)

    result = h.search_clawhub(query="testing")
    assert result["results"][0]["slug"] == "qa-testing"
