import httpx
import pytest

from agentnet_cli.plugins.claude_marketplace import (
    ClaudeMarketplaceClient,
    ClaudeMarketplaceError,
)

SAMPLE_CATALOG = {
    "plugins": [
        {
            "name": "sql-helper",
            "description": "SQL query builder and optimizer",
            "category": "database",
            "author": {"name": "ACME"},
            "homepage": "https://example.com",
            "keywords": ["sql", "postgres"],
        },
        {
            "name": "deploy-bot",
            "description": "One-click deployment to AWS and GCP",
            "category": "deployment",
            "author": {"name": "CloudCo"},
            "homepage": "https://cloudco.dev",
        },
        {
            "name": "code-review",
            "description": "Automated security code review",
            "category": "security",
            "author": {"name": "SecTools"},
        },
    ],
}


def _transport(status: int = 200, body: dict | None = None):
    body = body if body is not None else SAMPLE_CATALOG

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _client(status: int = 200, body: dict | None = None) -> ClaudeMarketplaceClient:
    return ClaudeMarketplaceClient(
        http_client=httpx.Client(transport=_transport(status, body))
    )


class TestSearch:
    def test_happy_path(self):
        with _client() as c:
            result = c.search(query="sql")
        assert result["total"] == 1
        assert result["results"][0]["name"] == "sql-helper"
        assert result["source"] == "claude-plugins-official"

    def test_matches_description(self):
        with _client() as c:
            result = c.search(query="deployment")
        assert result["total"] == 1
        assert result["results"][0]["name"] == "deploy-bot"

    def test_matches_keywords(self):
        with _client() as c:
            result = c.search(query="postgres")
        assert result["total"] == 1
        assert result["results"][0]["name"] == "sql-helper"

    def test_category_filter(self):
        with _client() as c:
            result = c.search(query="", category="security")
        assert result["total"] == 1
        assert result["results"][0]["name"] == "code-review"

    def test_limit(self):
        with _client() as c:
            result = c.search(query="", limit=1)
        assert len(result["results"]) == 1
        assert result["total"] == 3

    def test_no_matches(self):
        with _client() as c:
            result = c.search(query="nonexistent_xyz")
        assert result["total"] == 0
        assert result["results"] == []

    def test_caches_catalog(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=SAMPLE_CATALOG)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        with ClaudeMarketplaceClient(http_client=http) as c:
            c.search(query="sql")
            c.search(query="deploy")
        assert len(calls) == 1

    def test_rate_limited(self):
        with _client(status=429, body={}) as c:
            with pytest.raises(ClaudeMarketplaceError, match="Rate limited"):
                c.search(query="anything")

    def test_server_error(self):
        with _client(status=500, body={}) as c:
            with pytest.raises(ClaudeMarketplaceError, match="server error"):
                c.search(query="anything")

    def test_generic_http_error(self):
        with _client(status=403, body={}) as c:
            with pytest.raises(ClaudeMarketplaceError, match="Request failed"):
                c.search(query="anything")
