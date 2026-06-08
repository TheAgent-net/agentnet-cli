from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "src" / "agentnet_cli"
DISCOVERY_BASE = PKG_ROOT / "integrations" / "shared" / "discovery-skill.base.md"
CONTEXT = REPO_ROOT / "src" / "agentnet_cli" / "connectors" / "templates" / "shared" / "context.md"

REQUIRED_PHRASES = (
    "agentnet_search",
    "search first",
)

FORBIDDEN_PHRASES = (
    "agentnet_use_agent",
    "agentnet_wallet",
    "agentnet_settle_session",
    "funded wallet",
)

SYNC_TARGETS = (
    CONTEXT,
    PKG_ROOT / "integrations" / "claude" / "plugin" / "skills" / "agentnet" / "SKILL.md",
    PKG_ROOT / "integrations" / "openclaw" / "skills" / "agentnet" / "SKILL.md",
    REPO_ROOT / "src" / "agentnet_cli" / "tools" / "hermes" / "skills" / "agentnet" / "SKILL.md",
    REPO_ROOT / "src" / "agentnet_cli" / "connectors" / "templates" / "cursor" / "agentnet.mdc",
    PKG_ROOT / "integrations" / "claude" / "plugin" / "agents" / "marketplace.md",
)


@pytest.mark.parametrize("path", SYNC_TARGETS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_discovery_templates_include_canonical_phrases(path: Path):
    content = path.read_text()
    lowered = content.lower()
    for phrase in REQUIRED_PHRASES:
        assert phrase in lowered, f"{path.name} missing {phrase!r}"
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in content.lower(), f"{path.name} still contains {phrase!r}"


def test_discovery_base_matches_context():
    assert DISCOVERY_BASE.exists()
    assert DISCOVERY_BASE.read_text() == CONTEXT.read_text()


def test_mcp_search_tool_is_first():
    from agentnet_cli.tools.mcp_server import TOOL_DEFINITIONS

    assert TOOL_DEFINITIONS[0]["name"] == "agentnet_search"


def test_hermes_search_tool_is_first():
    from agentnet_cli.tools.hermes.schemas import SCHEMAS

    assert SCHEMAS[0]["name"] == "agentnet_search"
