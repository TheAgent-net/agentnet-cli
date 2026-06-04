import httpx
import pytest

from agentnet_cli.skills.client import SkillsClient, SkillsError


def _transport(status: int, body: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _client(status: int = 200, body: dict | None = None) -> SkillsClient:
    body = body or {}
    return SkillsClient(http_client=httpx.Client(transport=_transport(status, body)))


class TestSearch:
    def test_happy_path(self):
        payload = {
            "query": "testing",
            "searchType": "fuzzy",
            "skills": [{"id": "org/repo/skill", "name": "test-skill", "installs": 100, "source": "org/repo"}],
            "count": 1,
            "duration_ms": 50,
        }
        with _client(body=payload) as client:
            result = client.search(query="testing")
        assert result["skills"][0]["name"] == "test-skill"
        assert result["count"] == 1

    def test_passes_params(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"skills": [], "count": 0})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with SkillsClient(http_client=http) as client:
            client.search(query="react", limit=5)

        url = calls[0].url
        assert url.params["q"] == "react"
        assert url.params["limit"] == "5"
        assert "/api/search" in url.path

    def test_rate_limited(self):
        with _client(status=429, body={"error": "too many"}) as client:
            with pytest.raises(SkillsError, match="Rate limited"):
                client.search(query="anything")

    def test_server_error(self):
        with _client(status=500, body={}) as client:
            with pytest.raises(SkillsError, match="server error"):
                client.search(query="anything")

    def test_generic_http_error(self):
        with _client(status=400, body={}) as client:
            with pytest.raises(SkillsError, match="Request failed"):
                client.search(query="anything")
