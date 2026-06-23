from unittest.mock import patch

from typer.testing import CliRunner

from agentnet_cli.cli.main import app

runner = CliRunner()


def _invoke(args):
    with patch("agentnet_cli.tools.mcp_proxy.serve") as serve:
        result = runner.invoke(app, args)
    return result, serve


def test_upstream_exa_resolves_url():
    result, serve = _invoke(["mcp-proxy", "--upstream", "exa"])
    assert result.exit_code == 0
    serve.assert_called_once()
    assert serve.call_args.kwargs["upstream_url"] == "https://mcp.exa.ai/mcp"
    assert serve.call_args.kwargs["upstream_name"] == "exa"


def test_upstream_parallel_resolves_url():
    _result, serve = _invoke(["mcp-proxy", "--upstream", "parallel"])
    assert serve.call_args.kwargs["upstream_url"] == "https://search.parallel.ai/mcp"


def test_custom_upstream_url_overrides():
    _result, serve = _invoke(["mcp-proxy", "--upstream-url", "https://my/mcp"])
    assert serve.call_args.kwargs["upstream_url"] == "https://my/mcp"


def test_exa_api_key_appended():
    _result, serve = _invoke(["mcp-proxy", "--upstream", "exa", "--exa-api-key", "k123"])
    assert serve.call_args.kwargs["upstream_url"] == "https://mcp.exa.ai/mcp?exaApiKey=k123"


def test_unknown_upstream_errors():
    result, serve = _invoke(["mcp-proxy", "--upstream", "bing"])
    assert result.exit_code == 1
    serve.assert_not_called()


def test_missing_upstream_errors():
    result, serve = _invoke(["mcp-proxy"])
    assert result.exit_code == 1
    serve.assert_not_called()


def test_limit_and_timeout_forwarded():
    _result, serve = _invoke(
        ["mcp-proxy", "--upstream", "exa", "--limit", "3", "--slate-timeout", "1.5"]
    )
    assert serve.call_args.kwargs["slate_limit"] == 3
    assert serve.call_args.kwargs["slate_timeout"] == 1.5
