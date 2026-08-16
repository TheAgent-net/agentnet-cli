from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.config import save_config

runner = CliRunner()


def _mock_run_ok(*args, **kwargs):
    return MagicMock(returncode=0, stderr=b"")


def _setup_agents(home: Path) -> None:
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    (home / ".claude.json").write_text("{}")
    (home / ".cursor" / "extensions").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text("")
    (home / ".openclaw").mkdir()
    (home / ".openclaw" / "openclaw.json").write_text("{}")


def _tool_patches():
    return (
        patch("agentnet_cli.connectors.claude.find_executable", return_value="/usr/bin/claude"),
        patch("agentnet_cli.connectors.claude.run_tool", side_effect=_mock_run_ok),
        patch("agentnet_cli.connectors.openclaw.find_executable", return_value="/usr/bin/openclaw"),
        patch("agentnet_cli.connectors.openclaw.run_tool", side_effect=_mock_run_ok),
    )


def test_full_detect_connect_disconnect_cycle(fake_home):
    _setup_agents(fake_home)

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
    assert "openclaw" in result.stdout.lower()

    # Connect claude (subprocess calls mocked)
    with _tool_patches()[0], _tool_patches()[1], _tool_patches()[2], _tool_patches()[3]:
        result = runner.invoke(app, ["connect", "claude"])
    assert result.exit_code == 0
    assert "connected" in result.stdout.lower()

    # Status shows connected
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0

    # Disconnect
    with _tool_patches()[0], _tool_patches()[1], _tool_patches()[2], _tool_patches()[3]:
        result = runner.invoke(app, ["disconnect", "claude"])
    assert result.exit_code == 0
    assert "disconnected" in result.stdout.lower()


def test_connect_all_and_disconnect_all(fake_home):
    _setup_agents(fake_home)
    save_config({
        "platform_url": "https://test.agentnet.market",
        "api_token": "agn_test",
        "org_id": "org_1",
        "wallet_id": "wal_1",
    })

    p0, p1, p2, p3 = _tool_patches()
    with p0, p1, p2, p3:
        result = runner.invoke(app, ["connect", "--all"])
    assert result.exit_code == 0
    assert "claude" in result.stdout.lower()
    assert "cursor" in result.stdout.lower()
    assert "openclaw" in result.stdout.lower()

    p0, p1, p2, p3 = _tool_patches()
    with p0, p1, p2, p3:
        result = runner.invoke(app, ["disconnect", "--all"])
    assert result.exit_code == 0
