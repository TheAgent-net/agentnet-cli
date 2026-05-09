import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentnet_cli.main import app

runner = CliRunner()


def _mock_client(**method_returns):
    client = MagicMock()
    for method, retval in method_returns.items():
        getattr(client, method).return_value = retval
    return client


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_balance(mock_gc, mock_aid, fake_home):
    mock_gc.return_value = _mock_client(
        wallet_balance={"balance": 42.50, "currency": "USD"}
    )
    result = runner.invoke(app, ["wallet", "balance"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["balance"] == 42.50
    mock_gc.return_value.wallet_balance.assert_called_once_with(agent_id="agent-123")


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_history(mock_gc, mock_aid, fake_home):
    mock_gc.return_value = _mock_client(
        wallet_history={"transactions": [{"amount": -1.0, "type": "payment"}]}
    )
    result = runner.invoke(app, ["wallet", "history"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "transactions" in data


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_history_with_limit(mock_gc, mock_aid, fake_home):
    mock_gc.return_value = _mock_client(wallet_history={"transactions": []})
    result = runner.invoke(app, ["wallet", "history", "--limit", "10"])
    assert result.exit_code == 0
    mock_gc.return_value.wallet_history.assert_called_once_with(agent_id="agent-123", limit=10)


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_topup(mock_gc, mock_aid, fake_home):
    mock_gc.return_value = _mock_client(
        wallet_topup={"new_balance": 52.50, "added": 10.0}
    )
    result = runner.invoke(app, ["wallet", "topup", "10.0"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["new_balance"] == 52.50


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_balance_platform_error(mock_gc, mock_aid, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.wallet_balance.side_effect = PlatformError("Authentication failed")
    result = runner.invoke(app, ["wallet", "balance"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Authentication failed"


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_history_platform_error(mock_gc, mock_aid, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.wallet_history.side_effect = PlatformError("Platform server error")
    result = runner.invoke(app, ["wallet", "history"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Platform server error"


@patch("agentnet_cli.commands.wallet.get_agent_id", return_value="agent-123")
@patch("agentnet_cli.commands.wallet.get_client")
def test_wallet_topup_platform_error(mock_gc, mock_aid, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.wallet_topup.side_effect = PlatformError("Rate limited, try again later")
    result = runner.invoke(app, ["wallet", "topup", "10.0"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Rate limited, try again later"


def test_wallet_balance_no_auth(fake_home):
    result = runner.invoke(app, ["wallet", "balance"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert "Not authenticated" in data["error"] or "No agent registered" in data["error"]
