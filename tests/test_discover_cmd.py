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


@patch("agentnet_cli.commands.discover.get_client")
def test_discover_happy_path(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(
        discover={"listings": [{"name": "WeatherBot", "price": 1.0}]}
    )
    result = runner.invoke(app, ["discover", "weather"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "listings" in data


@patch("agentnet_cli.commands.discover.get_client")
def test_discover_with_options(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(discover={"listings": []})
    result = runner.invoke(app, ["discover", "food", "--category", "delivery", "--limit", "5", "--max-price", "10"])
    assert result.exit_code == 0
    mock_gc.return_value.discover.assert_called_once_with(
        query="food", category="delivery", max_results=5, max_price=10,
    )


@patch("agentnet_cli.commands.discover.get_client")
def test_discover_platform_error(mock_gc, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.discover.side_effect = PlatformError("Rate limited, try again later")
    result = runner.invoke(app, ["discover", "weather"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Rate limited, try again later"


def test_discover_no_auth(fake_home):
    result = runner.invoke(app, ["discover", "weather"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert "Not authenticated" in data["error"]


@patch("agentnet_cli.commands.discover.get_client")
def test_agents_happy_path(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(
        discover_agents={"agents": [{"name": "CodeBot", "id": "cb-1"}]}
    )
    result = runner.invoke(app, ["agents", "code review"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "agents" in data


@patch("agentnet_cli.commands.discover.get_client")
def test_agents_with_limit(mock_gc, fake_home):
    mock_gc.return_value = _mock_client(discover_agents={"agents": []})
    result = runner.invoke(app, ["agents", "weather", "--limit", "3"])
    assert result.exit_code == 0
    mock_gc.return_value.discover_agents.assert_called_once_with(query="weather", limit=3)


@patch("agentnet_cli.commands.discover.get_client")
def test_agents_platform_error(mock_gc, fake_home):
    from agentnet_cli.platform.client import PlatformError

    mock_gc.return_value = _mock_client()
    mock_gc.return_value.discover_agents.side_effect = PlatformError("Platform server error")
    result = runner.invoke(app, ["agents", "weather"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["error"] == "Platform server error"
