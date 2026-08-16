"""Tests for register_command() — registration flow, agent selection, error handling."""

from unittest.mock import patch

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.credentials import TIER_GUEST

runner = CliRunner()

_GUEST_CFG = {
    "platform_url": "https://api.agentnet.market",
    "api_token": "ank1_guest_claim",
    "org_id": "org_guest",
    "agent_id": "agt_guest",
    "tier": TIER_GUEST,
}


def _mock_browser_login(mock, info, api_token="browser_key"):
    mock.cli_login_start.return_value = {
        "login_id": "login_1",
        "verification_url": "https://app.agentnet.market/login?cli_login=device_1",
        "poll_secret": "poll_secret",
        "expires_in": 60,
        "poll_interval": 1,
    }
    mock.cli_login_poll.return_value = {"status": "authorized", "api_token": api_token, **info}


def _guest_bootstrap_patch():
    return patch(
        "agentnet_cli.cli.core.register.ensure_guest_credentials",
        return_value=_GUEST_CFG,
    )


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_new_user_existing_agent(_open, MockClient, _ensure_guest, fake_home):
    """Select an existing agent by index during registration."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_1",
        "org_name": "TestOrg",
        "agent_id": None,
        "agents": [
            {"agent_id": "ag_1", "name": "Bot", "status": "active", "agent_type": "consumer"},
        ],
    })
    result = runner.invoke(app, ["register"], input="1\n")
    assert result.exit_code == 0
    assert "Registered successfully" in result.stdout

    from agentnet_cli.infra.config import load_config

    cfg = load_config()
    assert cfg is not None
    assert cfg["agent_id"] == "ag_1"
    assert cfg["org_id"] == "org_1"
    assert cfg["tier"] == "authenticated"
    mock.cli_login_start.assert_called_once_with(claim_api_token="ank1_guest_claim")


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_new_user_create_agent(_open, MockClient, _ensure_guest, fake_home):
    """Create a brand-new agent when none exist in the org."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_2",
        "org_name": "EmptyOrg",
        "agent_id": None,
        "agents": [],
    })
    mock.cli_register_agent.return_value = {
        "agent_id": "ag_new",
        "agent_name": "MyBot",
        "visibility": "private",
        "api_key": "agn_newkey123",
        "seed_balance_usd": 5.0,
    }
    # Prompts: agent_name, visibility
    result = runner.invoke(app, ["register"], input="MyBot\nprivate\n")
    assert result.exit_code == 0
    assert "Created" in result.stdout
    mock.cli_register_agent.assert_called_once_with(
        name="MyBot", visibility="private", description="", url=""
    )
    mock.cli_login_start.assert_called_once_with(claim_api_token="ank1_guest_claim")


@patch("agentnet_cli.cli.core.register.PlatformClient")
def test_register_already_registered_decline(MockClient, fake_home):
    """Decline re-registration when already registered."""
    from agentnet_cli.infra.config import save_config

    save_config({"api_token": "existing", "platform_url": "https://x", "org_id": "o", "agent_id": "a"})

    result = runner.invoke(app, ["register"], input="n\n")
    assert result.exit_code == 0
    assert "Already registered" in result.stdout

    from agentnet_cli.infra.config import load_config

    cfg = load_config()
    assert cfg["api_token"] == "existing"


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_browser_login_start_fails(_open, MockClient, _ensure_guest, fake_home):
    """Registration fails when browser login cannot be started."""
    mock = MockClient.return_value
    mock.cli_login_start.side_effect = Exception("Unauthorized")

    result = runner.invoke(app, ["register"])
    assert result.exit_code != 0
    assert "Failed to start browser login" in result.stdout


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_negative_index(_open, MockClient, _ensure_guest, fake_home):
    """Entering '0' for agent selection is invalid (1-indexed)."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_1",
        "org_name": "TestOrg",
        "agent_id": None,
        "agents": [
            {"agent_id": "ag_1", "name": "Bot", "status": "active", "agent_type": "consumer"},
        ],
    })
    result = runner.invoke(app, ["register"], input="0\n")
    assert result.exit_code != 0
    assert "Invalid selection" in result.stdout


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_non_numeric_choice(_open, MockClient, _ensure_guest, fake_home):
    """Non-numeric, non-'new' input for agent selection is rejected."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_1",
        "org_name": "TestOrg",
        "agent_id": None,
        "agents": [
            {"agent_id": "ag_1", "name": "Bot", "status": "active", "agent_type": "consumer"},
        ],
    })
    result = runner.invoke(app, ["register"], input="abc\n")
    assert result.exit_code != 0
    assert "Invalid choice" in result.stdout


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_token_bound_to_agent(_open, MockClient, _ensure_guest, fake_home):
    """Token already bound to a specific agent — skip selection."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_3",
        "org_name": "BoundOrg",
        "agent_id": "ag_bound",
        "agent_name": "BoundBot",
        "agents": [],
    })
    result = runner.invoke(app, ["register"])
    assert result.exit_code == 0
    assert "Token bound to agent" in result.stdout or "Registered successfully" in result.stdout

    from agentnet_cli.infra.config import load_config

    cfg = load_config()
    assert cfg["agent_id"] == "ag_bound"
    assert cfg["tier"] == "authenticated"


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_choose_new_among_existing(_open, MockClient, _ensure_guest, fake_home):
    """Choose 'new' when agents exist — triggers agent creation."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_4",
        "org_name": "Org",
        "agent_id": None,
        "agents": [
            {"agent_id": "ag_old", "name": "Old", "status": "active", "agent_type": "consumer"},
        ],
    })
    mock.cli_register_agent.return_value = {
        "agent_id": "ag_fresh",
        "agent_name": "FreshBot",
        "visibility": "private",
    }
    # Prompts: choice=new, name, visibility
    result = runner.invoke(app, ["register"], input="new\nFreshBot\nprivate\n")
    assert result.exit_code == 0
    assert "Created" in result.stdout
    mock.cli_register_agent.assert_called_once()


@_guest_bootstrap_patch()
@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_out_of_range_index(_open, MockClient, _ensure_guest, fake_home):
    """Entering an index > number of agents is invalid."""
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_1",
        "org_name": "TestOrg",
        "agent_id": None,
        "agents": [
            {"agent_id": "ag_1", "name": "Bot", "status": "active", "agent_type": "consumer"},
        ],
    })
    result = runner.invoke(app, ["register"], input="99\n")
    assert result.exit_code != 0
    assert "Invalid selection" in result.stdout


@patch("agentnet_cli.cli.core.register.PlatformClient")
@patch("agentnet_cli.cli.core.register.webbrowser.open", return_value=True)
def test_register_guest_skips_already_registered_prompt(_open, MockClient, fake_home):
    """Guest credentials are claimed during login; no re-register prompt."""
    from agentnet_cli.infra.config import load_config, save_config

    save_config(dict(_GUEST_CFG))
    mock = MockClient.return_value
    _mock_browser_login(mock, {
        "org_id": "org_1",
        "org_name": "TestOrg",
        "agent_id": "ag_1",
        "agent_name": "Bot",
        "agents": [],
    })

    with patch(
        "agentnet_cli.cli.core.register.ensure_guest_credentials",
        return_value=_GUEST_CFG,
    ) as ensure_guest:
        result = runner.invoke(app, ["register"])

    assert result.exit_code == 0
    assert "Already registered" not in result.stdout
    ensure_guest.assert_called_once()
    mock.cli_login_start.assert_called_once_with(claim_api_token="ank1_guest_claim")
    cfg = load_config()
    assert cfg["tier"] == "authenticated"
    assert cfg["api_token"] == "browser_key"


@patch("agentnet_cli.cli.core.register.ensure_guest_credentials")
@patch("agentnet_cli.cli.core.register.PlatformClient")
def test_register_bootstrap_failure(MockClient, ensure_guest, fake_home):
    """Registration fails when guest bootstrap cannot mint a token."""
    ensure_guest.side_effect = RuntimeError("bootstrap down")

    result = runner.invoke(app, ["register"])
    assert result.exit_code != 0
    assert "Failed to bootstrap guest credentials" in result.stdout
    MockClient.assert_not_called()
