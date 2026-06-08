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


@patch("agentnet_cli.cli.marketplace.search._platform_client")
def test_search_platform_all(mock_platform, fake_home):
    mock_platform.return_value = _mock_client(search={"query": "weather", "sources": ["agents"]})

    result = runner.invoke(app, ["search", "weather"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["query"] == "weather"
    mock_platform.return_value.search.assert_called_once_with(
        query="weather",
        kind="all",
        category=None,
        limit=20,
        max_price=None,
    )


@patch("agentnet_cli.cli.marketplace.search._platform_client")
def test_search_platform_options(mock_platform, fake_home):
    mock_platform.return_value = _mock_client(search={"query": "food", "sources": ["listings"]})

    result = runner.invoke(
        app,
        ["search", "food", "--type", "listings", "--category", "delivery", "--limit", "5", "--max-price", "10"],
    )

    assert result.exit_code == 0
    mock_platform.return_value.search.assert_called_once_with(
        query="food",
        kind="listings",
        category="delivery",
        limit=5,
        max_price=10,
    )


@patch("agentnet_cli.cli.marketplace.search.SkillDiscovery")
def test_search_skills_uses_unified_discovery(mock_cls, fake_home):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.discover.return_value = {"results": [{"name": "react-test"}]}
    mock_cls.return_value = client

    result = runner.invoke(app, ["search", "react testing", "--type", "skills", "--limit", "3"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["results"][0]["name"] == "react-test"
    client.discover.assert_called_once_with(use_case="react testing", limit=3)


def test_removed_skills_group(fake_home):
    result = runner.invoke(app, ["skills", "search", "testing"])
    assert result.exit_code != 0


def test_removed_plugins_group(fake_home):
    result = runner.invoke(app, ["plugins", "search-claude", "testing"])
    assert result.exit_code != 0
