from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "src" / "agentnet_cli"
DISCOVERY_BASE = PKG_ROOT / "integrations" / "shared" / "discovery-skill.base.md"
CONTEXT = REPO_ROOT / "src" / "agentnet_cli" / "connectors" / "templates" / "shared" / "context.md"

REQUIRED_PHRASES = (
    "agentnet_discover_agents",
)

FORBIDDEN_PHRASES = (
    "agentnet_use_agent",
    "agentnet_wallet",
    "agentnet_settle_session",
    "funded wallet",
)

# Harnesses on the *pull* model: the prime tells the agent to go discover skills itself.
# Cursor is deliberately excluded — it runs the *push* model (hooks surface skills automatically),
# so its rule must NOT tell the agent to search. See test_cursor_rule_defers_to_the_hook.
SYNC_TARGETS = (
    CONTEXT,
    PKG_ROOT / "integrations" / "claude" / "plugin" / "skills" / "agentnet" / "SKILL.md",
    PKG_ROOT / "integrations" / "openclaw" / "skills" / "agentnet" / "SKILL.md",
    REPO_ROOT / "src" / "agentnet_cli" / "tools" / "hermes" / "skills" / "agentnet" / "SKILL.md",
    PKG_ROOT / "integrations" / "claude" / "plugin" / "agents" / "marketplace.md",
)

CURSOR_RULE = (
    REPO_ROOT / "src" / "agentnet_cli" / "connectors" / "templates" / "cursor" / "agentnet.mdc"
)
CURSOR_AGENT = (
    REPO_ROOT / "src" / "agentnet_cli" / "connectors" / "templates" / "cursor" / "agent.md"
)


@pytest.mark.parametrize("path", SYNC_TARGETS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_discovery_templates_include_canonical_phrases(path: Path):
    content = path.read_text()
    lowered = content.lower()
    for phrase in REQUIRED_PHRASES:
        assert phrase in lowered, f"{path.name} missing {phrase!r}"
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in content.lower(), f"{path.name} still contains {phrase!r}"


def test_cursor_rule_defers_to_the_hook():
    """Cursor is push-model: the always-apply rule must not start a competing skill search.

    Regression: the old rule said "find an existing agent/skill via agentnet_discover_agents",
    which fired at prompt time — before the hook could steer — so the agent ran its own discovery
    and fetched skills from GitHub instead of surfacing the list the hook pushed it.
    """
    rule = CURSOR_RULE.read_text()
    assert "alwaysApply: true" in rule
    # Must not instruct proactive discovery...
    assert "{{CONTEXT}}" not in rule, "must not splice in the pull-model discovery prime"
    for pull in ("find an existing agent/skill", "always call agentnet_search"):
        assert pull not in rule.lower(), f"cursor rule still pushes the pull model: {pull!r}"
    # ...and must prime the behaviors the hook depends on.
    lowered = rule.lower()
    assert "exactly as written" in lowered, "rule must tell the agent to show the list as written"
    assert "agentnet match" in lowered, (
        "rule must call out the observed anti-pattern of collapsing the list to 'AgentNet match: X'"
    )
    assert "npx skills add" in lowered, (
        "rule must forbid installing skills — agents ran the install command when given one"
    )
    assert "skill.md" in lowered, "rule must tell the agent to read the on-disk SKILL.md"
    assert "do not" in lowered and "agentnet_discover_agents" in lowered, (
        "rule must explicitly forbid proactively calling the discovery tools"
    )


def test_cursor_agent_shim_does_not_contradict_the_rule():
    """Both Cursor files must agree on the push model.

    Regression: the rule said "never search yourself" while the agent shim still said "search the
    marketplace first using agentnet_search" and spliced in the pull prime. Cursor surfaced the
    clash in its own reasoning ("conflict between the agentnet skill and workspace rules") and
    burned a turn resolving it.
    """
    shim = CURSOR_AGENT.read_text()
    assert "{{CONTEXT}}" not in shim, "must not splice the pull-model discovery prime"
    lowered = shim.lower()
    assert "search the marketplace first" not in lowered
    assert "explicitly ask" in lowered, "shim must scope itself to explicit user requests"
    assert "do not invoke it proactively" in lowered
    # And it must not re-assert the automatic-discovery duty the rule forbids.
    assert "before building" not in lowered


def test_discovery_base_matches_context():
    assert DISCOVERY_BASE.exists()
    assert DISCOVERY_BASE.read_text() == CONTEXT.read_text()


def test_mcp_search_tool_is_first():
    from agentnet_cli.tools.mcp_server import TOOL_DEFINITIONS

    assert TOOL_DEFINITIONS[0]["name"] == "agentnet_search"


def test_hermes_search_tool_is_first():
    from agentnet_cli.tools.hermes.schemas import SCHEMAS

    assert SCHEMAS[0]["name"] == "agentnet_search"
