import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentnet_cli.cli.main import app

runner = CliRunner()


def _mock_client(**method_returns):
    client = MagicMock()
    for method, retval in method_returns.items():
        getattr(client, method).return_value = retval
    return client


@patch("agentnet_cli.cli.marketplace.agent.get_client")
def test_agent_happy_path(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(
        get_agent={"id": "wb-1", "name": "WeatherBot", "skills": ["forecast"], "price": 1.0}
    )
    result = runner.invoke(app, ["agent", "wb-1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "wb-1"
    assert data["name"] == "WeatherBot"


@patch("agentnet_cli.cli.marketplace.agent.get_client")
def test_agent_platform_error(mock_gc, fake_home):
    from agentnet_cli.marketplace.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.get_agent.side_effect = PlatformError("Authentication failed")
    result = runner.invoke(app, ["agent", "wb-1"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Authentication failed"


def test_agent_no_auth(fake_home):
    result = runner.invoke(app, ["agent", "wb-1"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert "Not authenticated" in data["error"]


def test_hire_command_not_exposed(fake_home):
    result = runner.invoke(app, ["hire", "wb-1", "--task", "do stuff"], catch_exceptions=False)
    assert result.exit_code != 0
