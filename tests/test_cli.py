from unittest.mock import patch
from typer.testing import CliRunner
from agentnet_cli.main import app

runner = CliRunner()


def test_detect_command(fake_home):
    result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "detected" in result.stdout.lower() or "not found" in result.stdout.lower()


def test_detect_shows_table_with_agents(fake_home):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude" / "settings.json").write_text("{}")
    result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "Claude" in result.stdout
    assert "ready" in result.stdout.lower() or "connected" in result.stdout.lower()


def test_detect_shows_binary_status(fake_home):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude" / "settings.json").write_text("{}")
    with patch("agentnet_cli.paths.shutil.which", return_value=None):
        result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "not in PATH" in result.stdout


def test_detect_shows_set_path_hint(fake_home):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude" / "settings.json").write_text("{}")
    with patch("agentnet_cli.paths.shutil.which", return_value=None):
        result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "set-path" in result.stdout


def test_detect_shows_summary_counts(fake_home):
    result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "0/7 detected" in result.stdout or "detected" in result.stdout


def test_detect_shows_display_names(fake_home):
    result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "GitHub Copilot" in result.stdout
    assert "VS Code" in result.stdout
    assert "OpenClaw" in result.stdout


def test_status_no_config(fake_home):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not registered" in result.stdout.lower()


def test_connect_no_agent_specified(fake_home):
    result = runner.invoke(app, ["connect"])
    assert result.exit_code != 0 or "error" in result.stdout.lower() or "not registered" in result.stdout.lower()


def test_connect_shows_usage_hint(fake_home):
    result = runner.invoke(app, ["connect"])
    assert "agentnet connect" in result.stdout.lower() or "register" in result.stdout.lower()


def test_set_path_command(fake_home):
    fake_bin = fake_home / "my-claude"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    result = runner.invoke(app, ["set-path", "claude", str(fake_bin)])
    assert result.exit_code == 0
    assert "Claude" in result.stdout

    from agentnet_cli.config import load_agent_paths
    assert load_agent_paths()["claude"] == str(fake_bin.resolve())


def test_set_path_warns_missing_file(fake_home):
    result = runner.invoke(app, ["set-path", "claude", "/nonexistent/path"])
    assert result.exit_code == 0
    assert "does not exist" in result.stdout


def test_set_path_rejects_unknown_agent(fake_home):
    result = runner.invoke(app, ["set-path", "unknown", "/some/path"])
    assert result.exit_code != 0


def test_set_path_shows_available_agents(fake_home):
    result = runner.invoke(app, ["set-path", "unknown", "/some/path"])
    assert "Available" in result.stdout or "available" in result.stdout.lower()


def test_clear_path_command(fake_home):
    from agentnet_cli.config import save_agent_path
    save_agent_path("claude", "/opt/claude")
    result = runner.invoke(app, ["clear-path", "claude"])
    assert result.exit_code == 0
    assert "Cleared" in result.stdout or "Claude" in result.stdout


def test_clear_path_nonexistent(fake_home):
    result = runner.invoke(app, ["clear-path", "claude"])
    assert result.exit_code == 0
    assert "No custom path" in result.stdout or "no custom path" in result.stdout.lower()


def test_version_flag(fake_home):
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_disconnect_no_agent_specified(fake_home):
    result = runner.invoke(app, ["disconnect"])
    assert result.exit_code != 0 or "error" in result.stdout.lower()


def test_update_command_already_latest(fake_home):
    """update when already on latest version just reports up-to-date."""
    from agentnet_cli import __version__

    with patch("agentnet_cli.updater.refresh_stale_connections", return_value=0), \
         patch("agentnet_cli.updater.check_pypi_latest", return_value=__version__):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "latest" in result.stdout.lower() or "up to date" in result.stdout.lower()


def test_update_command_pypi_unreachable(fake_home):
    """update when PyPI is unreachable still refreshes agent configs."""
    with patch("agentnet_cli.updater.refresh_stale_connections", return_value=0), \
         patch("agentnet_cli.updater.check_pypi_latest", return_value=None):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "Could not reach PyPI" in result.stdout


def test_disconnect_not_connected(fake_home):
    """Disconnect an agent that isn't connected — shows 'not connected'."""
    result = runner.invoke(app, ["disconnect", "claude"])
    assert result.exit_code == 0
    assert "not connected" in result.stdout.lower()


def test_connect_unknown_agent(fake_home):
    """Connect an unknown agent name — shows error with available list."""
    from agentnet_cli.config import save_config

    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    result = runner.invoke(app, ["connect", "foobar"])
    assert result.exit_code != 0
    assert "Unknown agent" in result.stdout or "unknown" in result.stdout.lower()


def test_connect_not_registered(fake_home):
    """Connect without prior registration — shows 'Not registered' error."""
    result = runner.invoke(app, ["connect", "claude"])
    assert result.exit_code != 0 or "not registered" in result.stdout.lower()
