from unittest.mock import MagicMock

import httpx

from agentnet_cli.skills.discovery import SkillDiscovery


def _mock_skills(results):
    client = MagicMock()
    client.search.return_value = {
        "skills": [{"id": r, "name": r.split("/")[-1], "installs": 100 - i, "source": "/".join(r.split("/")[:2])}
                   for i, r in enumerate(results)],
        "count": len(results),
    }
    return client


def _mock_skillsmp(results):
    client = MagicMock()
    client.search.return_value = {
        "data": {"skills": [{"id": r, "name": r, "description": f"desc of {r}", "stars": 50 - i}
                             for i, r in enumerate(results)]},
    }
    return client


def _mock_clawhub(results):
    client = MagicMock()
    client.search.return_value = {
        "results": [{"slug": r, "displayName": r.title(), "summary": f"summary {r}", "score": 3.0}
                    for r in results],
    }
    return client


def _mock_claude_mp(results):
    client = MagicMock()
    client.search.return_value = {
        "results": [{"name": r, "description": f"desc {r}", "category": "dev", "homepage": ""}
                    for r in results],
        "total": len(results),
        "source": "claude-plugins-official",
    }
    return client


class TestExpandQueriesDeterministic:
    def test_extracts_keywords(self):
        disco = SkillDiscovery(
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
        )
        queries = disco._expand_queries_deterministic("set up CI/CD pipeline for React app")
        assert any("react" in q for q in queries)
        assert any("ci" in q or "pipeline" in q for q in queries)
        assert len(queries) >= 2

    def test_handles_simple_input(self):
        disco = SkillDiscovery(
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
        )
        queries = disco._expand_queries_deterministic("testing")
        assert "testing" in queries


class TestDeduplicate:
    def test_deduplicates_by_name(self):
        disco = SkillDiscovery(
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
        )
        results = [
            {"name": "code-review", "source": "skills.sh", "installs": 100},
            {"name": "code-review", "source": "clawhub", "installs": 50},
            {"name": "testing", "source": "skills.sh", "installs": 200},
        ]
        unique = disco._deduplicate(results)
        assert len(unique) == 2
        cr = next(r for r in unique if r["name"] == "code-review")
        assert cr["installs"] == 100
        assert cr["source_count"] == 2

    def test_keeps_higher_installs(self):
        disco = SkillDiscovery(
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
        )
        results = [
            {"name": "react", "source": "clawhub", "installs": 500},
            {"name": "react", "source": "skills.sh", "installs": 1000},
        ]
        unique = disco._deduplicate(results)
        assert unique[0]["installs"] == 1000


class TestRankDeterministic:
    def test_ranks_by_source_count_then_installs(self):
        disco = SkillDiscovery(
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
        )
        results = [
            {"name": "a", "source_count": 1, "installs": 1000},
            {"name": "b", "source_count": 3, "installs": 10},
            {"name": "c", "source_count": 2, "installs": 500},
        ]
        ranked = disco._rank_deterministic(results)
        assert ranked[0]["name"] == "b"
        assert ranked[1]["name"] == "c"
        assert ranked[2]["name"] == "a"


class TestPlatformMode:
    def test_uses_platform_when_configured(self):
        platform_response = {
            "use_case": "react",
            "queries_used": ["react"],
            "ai_powered": True,
            "llm_provider": "openai",
            "sources_searched": ["skills.sh"],
            "total_found": 1,
            "results": [{"name": "react-skill", "source": "skills.sh"}],
        }

        def mock_handler(request: httpx.Request) -> httpx.Response:
            assert "/skills/discover" in str(request.url)
            assert request.url.params["use_case"] == "react development"
            return httpx.Response(200, json=platform_response)

        disco = SkillDiscovery(
            platform_url="https://app.agentnet.market",
            api_token="test-token",
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
            http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
        )
        result = disco.discover(use_case="react development", limit=5)
        assert result["ai_powered"] is True
        assert result["results"][0]["name"] == "react-skill"

    def test_falls_back_to_local_on_platform_error(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "down"})

        disco = SkillDiscovery(
            platform_url="https://app.agentnet.market",
            api_token="test-token",
            skills_client=_mock_skills(["org/repo/fallback-skill"]),
            skillsmp_client=_mock_skillsmp([]),
            clawhub_client=_mock_clawhub([]),
            claude_marketplace=_mock_claude_mp([]),
            http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
        )
        result = disco.discover(use_case="anything", limit=10)
        assert result["total_found"] >= 1

    def test_skips_platform_when_no_token(self):
        disco = SkillDiscovery(
            platform_url="https://app.agentnet.market",
            api_token=None,
            skills_client=_mock_skills(["org/repo/local-skill"]),
            skillsmp_client=_mock_skillsmp([]),
            clawhub_client=_mock_clawhub([]),
            claude_marketplace=_mock_claude_mp([]),
        )
        result = disco.discover(use_case="testing", limit=5)
        assert result["total_found"] >= 1


class TestDiscover:
    def test_aggregates_from_all_sources(self):
        disco = SkillDiscovery(
            skills_client=_mock_skills(["org/repo/react-skill"]),
            skillsmp_client=_mock_skillsmp(["react-patterns"]),
            clawhub_client=_mock_clawhub(["react-tools"]),
            claude_marketplace=_mock_claude_mp(["react-plugin"]),
        )
        result = disco.discover(use_case="react development", limit=10)
        assert result["ai_powered"] is False
        assert len(result["queries_used"]) >= 1
        assert result["total_found"] >= 1
        assert len(result["results"]) >= 1
        sources = {r["source"] for r in result["results"]}
        assert len(sources) >= 1

    def test_limits_results(self):
        disco = SkillDiscovery(
            skills_client=_mock_skills([f"org/repo/s{i}" for i in range(10)]),
            skillsmp_client=_mock_skillsmp([]),
            clawhub_client=_mock_clawhub([]),
            claude_marketplace=_mock_claude_mp([]),
        )
        result = disco.discover(use_case="testing", limit=3)
        assert len(result["results"]) <= 3

    def test_handles_source_failures(self):
        failing = MagicMock()
        failing.search.side_effect = RuntimeError("network down")
        disco = SkillDiscovery(
            skills_client=_mock_skills(["org/repo/working"]),
            skillsmp_client=failing,
            clawhub_client=failing,
            claude_marketplace=failing,
        )
        result = disco.discover(use_case="anything", limit=10)
        assert len(result["results"]) >= 1


class TestExpandQueriesAI:
    def test_uses_openai_when_key_set(self):
        def mock_post(url, **kwargs):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '["react testing", "ci cd", "deployment"]'}}],
            })

        http = httpx.Client(transport=httpx.MockTransport(mock_post))
        disco = SkillDiscovery(
            openai_api_key="sk-test-123",
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
            http_client=http,
        )
        queries = disco._expand_queries("set up CI/CD for React")
        assert queries == ["react testing", "ci cd", "deployment"]

    def test_uses_anthropic_when_key_set(self):
        def mock_post(url, **kwargs):
            return httpx.Response(200, json={
                "content": [{"text": '["react hooks", "state management"]'}],
            })

        http = httpx.Client(transport=httpx.MockTransport(mock_post))
        disco = SkillDiscovery(
            anthropic_api_key="sk-ant-test",
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
            http_client=http,
        )
        queries = disco._expand_queries("React state management")
        assert queries == ["react hooks", "state management"]

    def test_openai_preferred_over_anthropic(self):
        calls: list[httpx.Request] = []

        def mock_post(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '["query1"]'}}],
            })

        http = httpx.Client(transport=httpx.MockTransport(mock_post))
        disco = SkillDiscovery(
            openai_api_key="sk-openai",
            anthropic_api_key="sk-anthropic",
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
            http_client=http,
        )
        disco._expand_queries("test")
        assert "openai" in str(calls[0].url)

    def test_falls_back_on_llm_error(self):
        def mock_post(url, **kwargs):
            return httpx.Response(500, json={"error": "server error"})

        http = httpx.Client(transport=httpx.MockTransport(mock_post))
        disco = SkillDiscovery(
            openai_api_key="sk-test-123",
            skills_client=MagicMock(),
            skillsmp_client=MagicMock(),
            clawhub_client=MagicMock(),
            claude_marketplace=MagicMock(),
            http_client=http,
        )
        queries = disco._expand_queries("react testing")
        assert len(queries) >= 1
        assert any("react" in q for q in queries)

    def test_discover_reports_llm_provider(self):
        disco = SkillDiscovery(
            openai_api_key="sk-test",
            skills_client=_mock_skills(["org/repo/s1"]),
            skillsmp_client=_mock_skillsmp([]),
            clawhub_client=_mock_clawhub([]),
            claude_marketplace=_mock_claude_mp([]),
            http_client=httpx.Client(transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={
                    "choices": [{"message": {"content": '["testing"]'}}],
                })
            )),
        )
        result = disco.discover(use_case="testing", limit=5)
        assert result["ai_powered"] is True
        assert result["llm_provider"] == "openai"
