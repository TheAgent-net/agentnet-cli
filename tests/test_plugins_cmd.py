from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentnet_cli.main import app

runner = CliRunner()


class TestSearchClaude:
    def test_happy_path(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search.return_value = {
            "results": [{"name": "test-plugin"}],
            "total": 1,
            "source": "claude-plugins-official",
        }
        with patch(
            "agentnet_cli.plugins.claude_marketplace.ClaudeMarketplaceClient",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["plugins", "search-claude", "test"])
        assert result.exit_code == 0
        assert "test-plugin" in result.output

    def test_with_options(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search.return_value = {"results": [], "total": 0, "source": "claude-plugins-official"}
        with patch(
            "agentnet_cli.plugins.claude_marketplace.ClaudeMarketplaceClient",
            return_value=mock_client,
        ):
            result = runner.invoke(
                app, ["plugins", "search-claude", "db", "--limit", "5", "--category", "database"]
            )
        assert result.exit_code == 0
        mock_client.search.assert_called_once_with(query="db", limit=5, category="database")

    def test_error(self):
        from agentnet_cli.plugins.claude_marketplace import ClaudeMarketplaceError

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search.side_effect = ClaudeMarketplaceError("Network error")
        with patch(
            "agentnet_cli.plugins.claude_marketplace.ClaudeMarketplaceClient",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["plugins", "search-claude", "test"])
        assert result.exit_code == 1
        assert "Network error" in result.output


class TestSearchClawHub:
    def test_happy_path(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search.return_value = {
            "results": [{"slug": "qa-testing", "displayName": "QA Testing"}]
        }
        with patch(
            "agentnet_cli.plugins.clawhub.ClawHubClient",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["plugins", "search-clawhub", "testing"])
        assert result.exit_code == 0
        assert "qa-testing" in result.output

    def test_with_options(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search.return_value = {"results": []}
        with patch(
            "agentnet_cli.plugins.clawhub.ClawHubClient",
            return_value=mock_client,
        ):
            result = runner.invoke(
                app,
                ["plugins", "search-clawhub", "sec", "--limit", "10", "--category", "security", "--family", "skill"],
            )
        assert result.exit_code == 0
        mock_client.search.assert_called_once_with(
            query="sec", limit=10, category="security", family="skill"
        )

    def test_error(self):
        from agentnet_cli.plugins.clawhub import ClawHubError

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search.side_effect = ClawHubError("Rate limited")
        with patch(
            "agentnet_cli.plugins.clawhub.ClawHubClient",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["plugins", "search-clawhub", "test"])
        assert result.exit_code == 1
        assert "Rate limited" in result.output
