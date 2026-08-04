from unittest.mock import MagicMock, patch

from agentnet_cli.tools.skillfire import candidates

_MAKE = "agentnet_cli.infra.credentials.make_platform_client"

_RAW = {
    "query": "flags",
    "type": "skills",
    "results": [
        {
            "name": "flag-create",
            "repo": "ld/agent-skills",
            "url": "https://skills.example/1",
            "install_cmd": "npx skills add ld/agent-skills@flag-create",
            "description": "create flags",
            "score": 66,
        },
        {"repo": "z", "description": "no name — skipped"},
    ],
}


def test_get_skill_candidates():
    platform = MagicMock()
    platform.search.return_value = _RAW
    with patch(_MAKE, return_value=platform):
        text, skills = candidates.get_skill_candidates("flags", limit=6, timeout=8)
    assert "flag-create" in text
    assert skills["flag-create"]["repo"] == "ld/agent-skills"
    assert skills["flag-create"]["install_cmd"] == "npx skills add ld/agent-skills@flag-create"
    platform.close.assert_called_once()


def test_get_skill_candidates_best_effort():
    with patch(_MAKE, return_value=None):
        assert candidates.get_skill_candidates("x", limit=6, timeout=8) == ("", {})
    platform = MagicMock()
    platform.search.side_effect = RuntimeError()
    with patch(_MAKE, return_value=platform):
        assert candidates.get_skill_candidates("x", limit=6, timeout=8) == ("", {})


def test_get_skill_candidates_forwards_harness_and_session():
    platform = MagicMock()
    platform.search.return_value = _RAW
    with patch(_MAKE, return_value=platform):
        candidates.get_skill_candidates(
            "flags",
            limit=6,
            timeout=8,
            harness="hermes",
            session="s1",
        )
    platform.search.assert_called_once_with(
        query="flags",
        kind="skills",
        limit=6,
        harness="hermes",
        session="s1",
    )
