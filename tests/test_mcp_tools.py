import httpx
import pytest
from agentnet_cli.tools.handlers import ToolActions


@pytest.fixture()
def actions():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"query": "x", "type": "all", "results": []})
    )
    client = httpx.Client(transport=transport)
    return ToolActions(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=client,
    )


def _make_actions(handler_fn):
    transport = httpx.MockTransport(handler_fn)
    return ToolActions(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    )


def test_actions_context_manager_closes_client():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    platform_http = httpx.Client(transport=transport)
    with ToolActions(
        platform_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=platform_http,
    ) as actions:
        assert isinstance(actions, ToolActions)
    assert platform_http.is_closed


def test_search_unified_platform():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert req.url.params["q"] == "weather"
        assert req.url.params["type"] == "all"
        assert req.url.params["limit"] == "5"
        return httpx.Response(
            200,
            json={"query": "weather", "type": "all", "results": [{"id": "a1", "kind": "agent"}]},
        )

    h = _make_actions(handler)
    result = h.search(query="weather", limit=5)
    assert result["query"] == "weather"
    assert result["results"][0]["id"] == "a1"


def test_search_skills_type():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert req.url.params["type"] == "skills"
        return httpx.Response(
            200,
            json={
                "query": "react testing",
                "type": "skills",
                "results": [{"name": "react-test", "kind": "skill"}],
            },
        )

    h = _make_actions(handler)
    result = h.search(query="react testing", type="skills", limit=3)
    assert result["results"][0]["name"] == "react-test"


def test_only_search_action():
    h = _make_actions(lambda req: httpx.Response(200, json={"results": []}))
    assert hasattr(h, "search")
    assert not hasattr(h, "find_agents")
    assert not hasattr(h, "find_skills")
    assert not hasattr(h, "get_agent")
