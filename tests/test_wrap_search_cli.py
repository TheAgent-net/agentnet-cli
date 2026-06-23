import json

from typer.testing import CliRunner

from agentnet_cli.cli.main import app

runner = CliRunner()


def _cursor_with_exa(fake_home):
    root = fake_home / ".cursor"
    root.mkdir(parents=True)
    path = root / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"exa": {"url": "https://mcp.exa.ai/mcp"}}}, indent=2) + "\n")
    return path


def test_wrap_then_unwrap_cursor(fake_home, monkeypatch):
    monkeypatch.setattr("agentnet_cli.connectors.search_wrap.shutil.which", lambda _: "/usr/bin/agentnet")
    path = _cursor_with_exa(fake_home)
    before = path.read_text()

    result = runner.invoke(app, ["wrap-search", "cursor", "--upstream", "exa"])
    assert result.exit_code == 0
    assert "routes through AgentNet" in result.stdout
    assert "mcp-proxy" in path.read_text()

    result = runner.invoke(app, ["unwrap-search", "cursor"])
    assert result.exit_code == 0
    assert "restored" in result.stdout
    assert path.read_text() == before


def test_wrap_unknown_agent_errors(fake_home):
    result = runner.invoke(app, ["wrap-search", "bogus"])
    assert result.exit_code == 1
    assert "Unknown agent" in result.stdout


def test_wrap_manual_prints_block_without_files(fake_home):
    result = runner.invoke(app, ["wrap-search", "cursor", "--manual"])
    assert result.exit_code == 0
    assert "mcp-proxy" in result.stdout
    # no .cursor dir should be created in manual mode
    assert not (fake_home / ".cursor").exists()


def test_wrap_no_entry_reports_cleanly(fake_home):
    root = fake_home / ".cursor"
    root.mkdir(parents=True)
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {}}) + "\n")
    result = runner.invoke(app, ["wrap-search", "cursor"])
    assert result.exit_code == 0
    assert "no exa" in result.stdout.lower()
