from unittest.mock import patch

from agentnet_cli.tools.skillfire import broker, config

_CREDS = "agentnet_cli.tools.skillfire.config.resolve_credentials"
_USE_AGENT = "agentnet_cli.marketplace.client.PlatformClient.use_agent"


# ── negotiate_via_platform (brokered A2A via use_agent) ──────────────────────
def test_negotiate_via_platform_happy():
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "settled", "agent_response": "Use skills/foo"}),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == "Use skills/foo"


def test_negotiate_via_platform_best_effort():
    with patch(_CREDS, return_value=None):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # no identity
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, side_effect=RuntimeError("boom")),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # platform error
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "settled"}),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # no agent_response
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "refunded",
                                        "agent_response": "agent turn exceeded 25s budget"}),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # failed turn not injected


def test_skills_agent_id_default_and_override(monkeypatch):
    monkeypatch.delenv("AGENTNET_SKILLS_AGENT_ID", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert broker.skills_agent_id() == config.SKILLS_AGENT_ID_DEFAULT == "agentnet-skills-agent"
    monkeypatch.setenv("AGENTNET_SKILLS_AGENT_ID", "other-agent")
    assert broker.skills_agent_id() == "other-agent"


def test_broker_fallback_is_labelled_as_not_on_disk(monkeypatch):
    # The Skills Agent cites conventional install paths for skills that were never installed here.
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.content.build_content_outcome", lambda *a, **k: ""
    )
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.broker.negotiate_via_platform",
        lambda *a, **k: "Use ~/.agentnet/skills/foo/bar/SKILL.md",
    )
    out = broker.upgrade_outcome("q", [{"name": "A", "why": "w"}], {}, timeout=5)
    assert "do not look for these files on disk" in out
    assert "Skills Agent" in out
