import json
from pathlib import Path
from typer.testing import CliRunner
from agentnet_cli.main import app
from agentnet_cli.config import save_config

runner = CliRunner()


def _setup_agents(home: Path) -> None:
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    (home / ".claude.json").write_text("{}")
    (home / ".cursor" / "extensions").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text("")


def test_full_detect_connect_disconnect_cycle(fake_home):
    _setup_agents(fake_home)

    # Register
    save_config({
        "platform_url": "https://test.agentnet.market",
        "api_token": "agn_test123",
        "org_id": "org_1",
        "wallet_id": "wal_1",
    })

    # Detect
    result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "claude" in result.stdout.lower()
    assert "cursor" in result.stdout.lower()

    # Connect claude
    result = runner.invoke(app, ["connect", "claude"])
    assert result.exit_code == 0
    assert "connected" in result.stdout.lower()

    # Verify files exist
    assert (fake_home / ".claude" / "skills" / "agentnet" / "SKILL.md").exists()
    mcp_data = json.loads((fake_home / ".claude.json").read_text())
    assert "agentnet" in mcp_data["mcpServers"]

    # Status shows connected
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0

    # Disconnect
    result = runner.invoke(app, ["disconnect", "claude"])
    assert result.exit_code == 0
    assert "disconnected" in result.stdout.lower()

    # Verify cleanup
    assert not (fake_home / ".claude" / "skills" / "agentnet" / "SKILL.md").exists()
    mcp_data = json.loads((fake_home / ".claude.json").read_text())
    assert "agentnet" not in mcp_data.get("mcpServers", {})


def test_connect_all_and_disconnect_all(fake_home):
    _setup_agents(fake_home)
    save_config({
        "platform_url": "https://test.agentnet.market",
        "api_token": "agn_test",
        "org_id": "org_1",
        "wallet_id": "wal_1",
    })

    result = runner.invoke(app, ["connect", "--all"])
    assert result.exit_code == 0
    assert "claude" in result.stdout.lower()
    assert "cursor" in result.stdout.lower()

    result = runner.invoke(app, ["disconnect", "--all"])
    assert result.exit_code == 0
