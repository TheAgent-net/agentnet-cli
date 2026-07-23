from unittest.mock import patch

from agentnet_cli.tools.skillfire import candidates

_CREDS = "agentnet_cli.tools.skillfire.config.resolve_credentials"
_DISCOVER_SKILLS = "agentnet_cli.marketplace.skills.discovery.SkillDiscovery.discover"

_RAW_SKILLS = {
    "results": [
        {"name": "flag-create", "source": "skills.sh", "repo": "ld/agent-skills",
         "url": "https://skills.sh/1", "install_cmd": "npx skills add ld/agent-skills@flag-create",
         "description": "create flags", "score": 66},
        {"name": "elsewhere", "source": "clawhub", "repo": "x/y", "description": "not skills.sh"},
        {"source": "skills.sh", "repo": "z", "description": "no name — skipped"},
    ]
}


def test_fetch_skill_candidates():
    with patch(_CREDS, return_value=("t", "p")), patch(_DISCOVER_SKILLS, return_value=_RAW_SKILLS):
        text, skills = candidates.fetch_skill_candidates("flags", limit=6, timeout=8)
    assert "flag-create" in text
    assert "elsewhere" not in text and "no name" not in text  # non-skills.sh + no-name dropped
    assert skills["flag-create"]["repo"] == "ld/agent-skills"
    assert skills["flag-create"]["install_cmd"] == "npx skills add ld/agent-skills@flag-create"


def test_fetch_skill_candidates_best_effort():
    with patch(_CREDS, return_value=None):
        assert candidates.fetch_skill_candidates("x", limit=6, timeout=8) == ("", {})
    with patch(_CREDS, return_value=("t", "p")), patch(_DISCOVER_SKILLS, side_effect=RuntimeError()):
        assert candidates.fetch_skill_candidates("x", limit=6, timeout=8) == ("", {})
