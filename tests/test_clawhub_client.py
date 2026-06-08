import httpx
import pytest

from agentnet_cli.marketplace.catalogs.clawhub import ClawHubClient, ClawHubError


def _transport(status: int, body: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _client(status: int = 200, body: dict | None = None) -> ClawHubClient:
    body = body or {}
    return ClawHubClient(http_client=httpx.Client(transport=_transport(status, body)))


class TestSearch:
    def test_happy_path(self):
        payload = {
            "results": [
                {"score": 3.0, "slug": "qa-testing", "displayName": "QA Testing"}
            ]
        }
        with _client(body=payload) as c:
            result = c.search(query="testing")
        assert result["results"][0]["slug"] == "qa-testing"

    def test_passes_all_params(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"results": []})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with ClawHubClient(http_client=http) as c:
            c.search(query="test", limit=5, category="security", family="code-plugin")

        url = calls[0].url
        assert url.params["q"] == "test"
        assert url.params["limit"] == "5"
        assert url.params["category"] == "security"
        assert url.params["family"] == "code-plugin"

    def test_omits_optional_params(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"results": []})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with ClawHubClient(http_client=http) as c:
            c.search(query="test")

        params = dict(calls[0].url.params)
        assert "category" not in params
        assert "family" not in params

    def test_rate_limited(self):
        with _client(status=429, body={"error": "too many"}) as c:
            with pytest.raises(ClawHubError, match="Rate limited"):
                c.search(query="anything")

    def test_server_error(self):
        with _client(status=500, body={}) as c:
            with pytest.raises(ClawHubError, match="server error"):
                c.search(query="anything")

    def test_generic_http_error(self):
        with _client(status=400, body={}) as c:
            with pytest.raises(ClawHubError, match="Request failed"):
                c.search(query="anything")


class TestBrowse:
    def test_happy_path(self):
        payload = {"items": [{"slug": "top-skill"}], "nextCursor": None}
        with _client(body=payload) as c:
            result = c.browse(limit=5, sort="stars")
        assert result["items"][0]["slug"] == "top-skill"

    def test_passes_params(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"items": []})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with ClawHubClient(http_client=http) as c:
            c.browse(limit=10, sort="trending")

        url = calls[0].url
        assert "/api/v1/skills" in url.path
        assert url.params["limit"] == "10"
        assert url.params["sort"] == "trending"
