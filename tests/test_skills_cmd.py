import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentnet_cli.main import app

runner = CliRunner()


def _mock_client(**method_returns):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    for method, retval in method_returns.items():
        getattr(client, method).return_value = retval
    return client


@patch("agentnet_cli.commands.skills.SkillsClient")
def test_search_happy_path(mock_cls, fake_home):
    payload = {
        "data": [{"id": "s1", "name": "code-review", "author": "alice"}],
        "pagination": {"page": 1, "total": 1, "hasNext": False},
    }
    mock_cls.return_value = _mock_client(search=payload)
    result = runner.invoke(app, ["skills", "search", "code review"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["data"][0]["name"] == "code-review"


@patch("agentnet_cli.commands.skills.SkillsClient")
def test_search_with_options(mock_cls, fake_home):
    mock_cls.return_value = _mock_client(search={"data": []})
    result = runner.invoke(app, [
        "skills", "search", "test",
        "--limit", "5",
        "--page", "2",
        "--sort", "stars",
        "--category", "data-ai",
    ])
    assert result.exit_code == 0
    mock_cls.return_value.search.assert_called_once_with(
        query="test", limit=5, page=2, sort_by="stars", category="data-ai",
    )


@patch("agentnet_cli.commands.skills.SkillsClient")
def test_search_error(mock_cls, fake_home):
    from agentnet_cli.skills.client import SkillsError

    client = _mock_client()
    client.search.side_effect = SkillsError("Rate limited — try again later")
    mock_cls.return_value = client
    result = runner.invoke(app, ["skills", "search", "anything"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert "Rate limited" in data["error"]


def test_search_no_query(fake_home):
    result = runner.invoke(app, ["skills", "search"])
    assert result.exit_code != 0
