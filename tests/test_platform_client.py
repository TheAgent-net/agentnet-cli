import json

import httpx
import pytest
from agentnet_cli.marketplace.client import PlatformClient, PlatformError, _validate_path_segment


def _make_client(transport):
    return PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    )


def test_search_endpoint():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert req.url.params["q"] == "translation"
        assert req.url.params["type"] == "all"
        assert req.url.params["limit"] == "7"
        assert req.url.params["harness"] == "claude"
        assert req.url.params["session_id"] == "sess-1"
        return httpx.Response(
            200,
            json={"query": "translation", "type": "all", "results": [{"id": "a1", "kind": "agent"}]},
        )

    c = _make_client(httpx.MockTransport(handler))
    result = c.search(
        query="translation",
        kind="all",
        limit=7,
        harness="claude",
        session="sess-1",
    )
    assert result["query"] == "translation"
    assert result["results"][0]["id"] == "a1"


def test_search_skills_kind():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/"
        assert req.url.params["type"] == "skills"
        return httpx.Response(
            200,
            json={
                "query": "react",
                "type": "skills",
                "results": [{"name": "skill-a", "kind": "skill"}],
            },
        )

    c = _make_client(httpx.MockTransport(handler))
    result = c.search(query="react", kind="skills", limit=10)
    assert [r["name"] for r in result["results"]] == ["skill-a"]


def test_auth_header_sent():
    def check_auth(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer agn_test"
        return httpx.Response(200, json={"query": "test", "type": "all", "results": []})

    c = _make_client(httpx.MockTransport(check_auth))
    c.search(query="test")


def test_send_telemetry_posts_best_effort_payload():
    from agentnet_cli import __version__

    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={})

    c = _make_client(httpx.MockTransport(handler))
    c.send_telemetry(
        event_type="cli_setup_complete",
        connector="claude",
        metadata={"connectors": "claude,codex"},
    )

    assert seen["path"] == "/auth/telemetry"
    assert seen["auth"] == "Bearer agn_test"
    assert seen["body"] == {
        "event_type": "cli_setup_complete",
        "cli_version": __version__,
        "connector": "claude",
        "metadata": {"connectors": "claude,codex"},
    }


def test_send_telemetry_skips_without_token():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        return httpx.Response(200, json={})

    c = PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    c.send_telemetry(event_type="cli_setup")
    assert seen == []


def test_send_telemetry_ignores_transport_errors():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=req)

    c = _make_client(httpx.MockTransport(handler))
    c.send_telemetry(event_type="cli_setup")


def test_handle_response_401():
    c = _make_client(
        httpx.MockTransport(lambda req: httpx.Response(401, json={"detail": "unauthorized"}))
    )
    with pytest.raises(PlatformError, match="Authentication failed"):
        c.search(query="test")


def test_handle_response_429():
    c = _make_client(
        httpx.MockTransport(lambda req: httpx.Response(429, json={"detail": "too many"}))
    )
    with pytest.raises(PlatformError, match="Rate limited"):
        c.search(query="test")


def test_handle_response_500():
    c = _make_client(
        httpx.MockTransport(lambda req: httpx.Response(500, json={"detail": "internal"}))
    )
    with pytest.raises(PlatformError, match="Platform server error"):
        c.search(query="test")


def test_validate_path_segment_traversal():
    with pytest.raises(PlatformError, match="Invalid identifier"):
        _validate_path_segment("../admin")


def test_get_agent_validates_id():
    c = _make_client(httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    with pytest.raises(PlatformError, match="Invalid identifier"):
        c.get_agent(agent_id="../admin")


def test_get_skill():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/discover/skills/org/react-testing"
        return httpx.Response(200, json={"id": "org/react-testing"})

    c = _make_client(httpx.MockTransport(handler))
    result = c.get_skill(skill_id="skill:org/react-testing")
    assert result["id"] == "org/react-testing"


def test_get_skill_validates_id():
    c = _make_client(httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    with pytest.raises(PlatformError, match="Invalid identifier"):
        c.get_skill(skill_id="../admin")


def test_context_manager():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"query": "test", "type": "all", "results": []})
    )
    with PlatformClient(
        base_url="https://test.agentnet.market",
        api_token="agn_test",
        http_client=httpx.Client(transport=transport),
    ) as c:
        result = c.search(query="test")
        assert result["results"] == []


def test_user_agent_header():
    def check_ua(req: httpx.Request) -> httpx.Response:
        assert "agentnet-cli/" in req.headers["user-agent"]
        return httpx.Response(200, json={"query": "test", "type": "all", "results": []})

    c = _make_client(httpx.MockTransport(check_ua))
    c.search(query="test")


def test_send_skill_recommendation_posts_feedback():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(204)

    c = _make_client(httpx.MockTransport(handler))
    c.send_skill_recommendation(
        use_case="review sql",
        recommended=[{"name": "Foo", "why": "helps", "score": "9"}],
        harness="claude",
        session="s9",
        classifier_model="claude-haiku",
        model=None,
    )
    assert seen["path"] == "/skills/discover/feedback"
    assert seen["body"] == {
        "use_case": "review sql",
        "recommended": [{"name": "Foo", "why": "helps", "score": "9"}],
        "harness": "claude",
        "session_id": "s9",
        "classifier_model": "claude-haiku",
    }


def test_no_use_agent_method():
    c = _make_client(httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    assert not hasattr(c, "use_agent")
    assert not hasattr(c, "find_agents")
    assert not hasattr(c, "find_skills")
