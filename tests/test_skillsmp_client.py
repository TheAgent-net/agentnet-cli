import httpx
import pytest

from agentnet_cli.skills.skillsmp import SkillsMPClient, SkillsMPError


def _transport(status: int, body: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _client(status: int = 200, body: dict | None = None) -> SkillsMPClient:
    body = body or {}
    return SkillsMPClient(http_client=httpx.Client(transport=_transport(status, body)))


class TestSearch:
    def test_happy_path(self):
        payload = {
            "data": [{"id": "s1", "name": "code-review", "author": "alice"}],
            "pagination": {"page": 1, "total": 1, "hasNext": False},
        }
        with _client(body=payload) as client:
            result = client.search(query="code review")
        assert result["data"][0]["name"] == "code-review"

    def test_passes_all_params(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"data": []})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with SkillsMPClient(http_client=http) as client:
            client.search(query="test", limit=5, page=2, sort_by="stars", category="data-ai")

        url = calls[0].url
        assert url.params["q"] == "test"
        assert url.params["limit"] == "5"
        assert url.params["page"] == "2"
        assert url.params["sortBy"] == "stars"
        assert url.params["category"] == "data-ai"

    def test_omits_category_when_none(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"data": []})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with SkillsMPClient(http_client=http) as client:
            client.search(query="test")

        assert "category" not in dict(calls[0].url.params)

    def test_rate_limited(self):
        with _client(status=429, body={"error": "too many"}) as client:
            with pytest.raises(SkillsMPError, match="Rate limited"):
                client.search(query="anything")

    def test_server_error(self):
        with _client(status=500, body={}) as client:
            with pytest.raises(SkillsMPError, match="server error"):
                client.search(query="anything")

    def test_generic_http_error(self):
        with _client(status=400, body={}) as client:
            with pytest.raises(SkillsMPError, match="Request failed"):
                client.search(query="anything")
