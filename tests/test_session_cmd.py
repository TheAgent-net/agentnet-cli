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


@patch("agentnet_cli.commands.session.get_client")
def test_session_continue(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(
        continue_session={"status": "escrowed", "reply": "Still working on it"}
    )
    result = runner.invoke(app, ["session", "continue", "sess-abc", "--message", "Any update?"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "escrowed"
    mock_gc.return_value.continue_session.assert_called_once_with(
        session_id="sess-abc", message="Any update?",
    )


@patch("agentnet_cli.commands.session.get_client")
def test_session_continue_platform_error(mock_gc, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.continue_session.side_effect = PlatformError("Request failed (404)")
    result = runner.invoke(app, ["session", "continue", "sess-abc", "--message", "hello"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert "404" in data["error"]


def test_session_continue_missing_message(fake_home):
    result = runner.invoke(app, ["session", "continue", "sess-abc"])
    assert result.exit_code != 0


@patch("agentnet_cli.commands.session.get_client")
def test_session_settle(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(
        settle_session={"status": "settled", "amount": 2.50}
    )
    result = runner.invoke(app, ["session", "settle", "sess-abc"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "settled"
    mock_gc.return_value.settle_session.assert_called_once_with(session_id="sess-abc")


@patch("agentnet_cli.commands.session.get_client")
def test_session_settle_platform_error(mock_gc, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.settle_session.side_effect = PlatformError("Authentication failed")
    result = runner.invoke(app, ["session", "settle", "sess-abc"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Authentication failed"


def test_session_continue_no_auth(fake_home):
    result = runner.invoke(app, ["session", "continue", "sess-abc", "--message", "hi"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert "Not authenticated" in data["error"]
