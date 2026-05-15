from unittest.mock import patch
from contextlib import nullcontext

from typer.testing import CliRunner
from agentnet_cli.agents.base import DetectionResult
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
    assert "agentnet connect" in result.stdout.lower() or "setup" in result.stdout.lower()


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
    assert "0.2.0" in result.stdout


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


def test_setup_registers_when_missing_config(fake_home):
    with patch("agentnet_cli.setup.register_command") as register, \
         patch("agentnet_cli.setup.detect_all", return_value=[]), \
         patch("agentnet_cli.setup.connect_command") as connect:
        result = runner.invoke(app, ["setup", "--url", "http://localhost:8006"])

    assert result.exit_code == 0
    register.assert_called_once()
    assert register.call_args.kwargs["platform_url"] == "http://localhost:8006"
    assert register.call_args.kwargs["auto_visibility"] == "private"
    assert register.call_args.kwargs["auto_agent_name"]
    connect.assert_not_called()


def test_setup_connects_all_detected_agents_by_default(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "tok", "platform_url": "https://x", "org_id": "o", "agent_id": "a"})
    detections = [
        DetectionResult(agent_name="claude", detected=True),
        DetectionResult(agent_name="cursor", detected=False),
    ]

    with patch("agentnet_cli.setup.detect_all", return_value=detections), \
         patch("agentnet_cli.setup.connect_command") as connect:
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    assert "Claude" in result.stdout
    assert "will configure" in result.stdout
    connect.assert_called_once_with(connect_all=True)


def test_setup_can_select_individual_detected_agent(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "tok", "platform_url": "https://x", "org_id": "o", "agent_id": "a"})
    detections = [
        DetectionResult(agent_name="claude", detected=True),
        DetectionResult(agent_name="cursor", detected=True),
    ]

    with patch("agentnet_cli.setup.detect_all", return_value=detections), \
         patch("agentnet_cli.setup.connect_command") as connect:
        result = runner.invoke(app, ["setup"], input="2\n1\n")

    assert result.exit_code == 0
    connect.assert_called_once_with(agent_name="claude")


def test_setup_individual_mode_defaults_to_no_agents(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "tok", "platform_url": "https://x", "org_id": "o", "agent_id": "a"})
    detections = [
        DetectionResult(agent_name="claude", detected=True),
        DetectionResult(agent_name="cursor", detected=True),
    ]

    with patch("agentnet_cli.setup.detect_all", return_value=detections), \
         patch("agentnet_cli.setup.connect_command") as connect:
        result = runner.invoke(app, ["setup"], input="2\n\n")

    assert result.exit_code == 0
    assert "No agents configured" in result.stdout
    connect.assert_not_called()


def test_setup_can_skip_agent_configuration(fake_home):
    from agentnet_cli.config import save_config

    save_config({"api_token": "tok", "platform_url": "https://x", "org_id": "o", "agent_id": "a"})
    detections = [DetectionResult(agent_name="claude", detected=True)]

    with patch("agentnet_cli.setup.detect_all", return_value=detections), \
         patch("agentnet_cli.setup.connect_command") as connect:
        result = runner.invoke(app, ["setup"], input="3\n")

    assert result.exit_code == 0
    assert "No agents configured" in result.stdout
    connect.assert_not_called()


def test_setup_menu_drawer_resets_columns(monkeypatch):
    import io
    from agentnet_cli import setup

    output = io.StringIO()
    monkeypatch.setattr(setup.sys, "stdout", output)

    assert setup._draw_menu(["one", "two"], previous_line_count=2) == 2

    assert output.getvalue() == "\033[2F\r\r\033[2Kone\r\n\r\033[2Ktwo\r\n"


def test_setup_tui_enter_selects_highlighted_agent(monkeypatch):
    from agentnet_cli import setup

    monkeypatch.setattr(setup, "_use_terminal_menu", lambda: True)
    monkeypatch.setattr(setup, "_raw_terminal", nullcontext)
    monkeypatch.setattr(setup, "_hidden_cursor", nullcontext)
    monkeypatch.setattr(setup, "_draw_menu", lambda lines, previous_line_count: len(lines))
    keys = iter(["enter"])
    monkeypatch.setattr(setup, "_read_key", lambda: next(keys))

    assert setup._multi_select_menu(
        "Choose",
        ["GitHub Copilot", "Codex", "Hermes"],
        default_selected=range(0),
    ) == [0]


def test_setup_tui_can_explicitly_select_none(monkeypatch):
    from agentnet_cli import setup

    monkeypatch.setattr(setup, "_use_terminal_menu", lambda: True)
    monkeypatch.setattr(setup, "_raw_terminal", nullcontext)
    monkeypatch.setattr(setup, "_hidden_cursor", nullcontext)
    monkeypatch.setattr(setup, "_draw_menu", lambda lines, previous_line_count: len(lines))
    keys = iter(["n", "enter"])
    monkeypatch.setattr(setup, "_read_key", lambda: next(keys))

    assert setup._multi_select_menu(
        "Choose",
        ["GitHub Copilot", "Codex", "Hermes"],
        default_selected=range(0),
    ) == []


def test_setup_tui_space_toggles_multiple_agents(monkeypatch):
    from agentnet_cli import setup

    monkeypatch.setattr(setup, "_use_terminal_menu", lambda: True)
    monkeypatch.setattr(setup, "_raw_terminal", nullcontext)
    monkeypatch.setattr(setup, "_hidden_cursor", nullcontext)
    monkeypatch.setattr(setup, "_draw_menu", lambda lines, previous_line_count: len(lines))
    keys = iter(["space", "down", "space", "enter"])
    monkeypatch.setattr(setup, "_read_key", lambda: next(keys))

    assert setup._multi_select_menu(
        "Choose",
        ["GitHub Copilot", "Codex", "Hermes"],
        default_selected=range(0),
    ) == [0, 1]


def test_hint_emitted_when_claudecode_set(fake_home, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    result = runner.invoke(app, ["detect"])
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "<claude-code-hint" in combined


def test_hint_not_emitted_normally(fake_home, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    result = runner.invoke(app, ["detect"])
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "<claude-code-hint" not in combined
