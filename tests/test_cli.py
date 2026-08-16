import os
from contextlib import nullcontext
from unittest.mock import patch

from typer.testing import CliRunner
from agentnet_cli.connectors.base import DetectionResult
from agentnet_cli.cli.main import app

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
    with patch("agentnet_cli.infra.paths.shutil.which", return_value=None):
        result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0
    assert "not in PATH" in result.stdout


def test_detect_shows_set_path_hint(fake_home):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude" / "settings.json").write_text("{}")
    with patch("agentnet_cli.infra.paths.shutil.which", return_value=None):
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

    from agentnet_cli.infra.config import load_agent_paths
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
    from agentnet_cli.infra.config import save_agent_path
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
    from agentnet_cli import __version__

    assert __version__ in result.stdout


def test_disconnect_no_agent_specified(fake_home):
    result = runner.invoke(app, ["disconnect"])
    assert result.exit_code != 0 or "error" in result.stdout.lower()


def test_update_command_already_latest(fake_home):
    """update when already on latest version just reports up-to-date."""
    from agentnet_cli import __version__

    with patch("agentnet_cli.cli.core.updater.clean_update") as mock_clean:
        from agentnet_cli.cli.core.updater import AutoUpdateResult

        mock_clean.return_value = AutoUpdateResult(
            checked=True,
            message=f"Already on latest version ({__version__})",
        )
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "latest" in result.stdout.lower() or "up to date" in result.stdout.lower()


def test_update_command_pypi_unreachable(fake_home):
    """update when PyPI is unreachable still refreshes agent configs."""
    with patch("agentnet_cli.cli.core.updater.clean_update") as mock_clean:
        from agentnet_cli.cli.core.updater import AutoUpdateResult

        mock_clean.return_value = AutoUpdateResult(
            checked=True,
            message="Could not reach PyPI",
        )
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
    from agentnet_cli.infra.config import save_config

    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    result = runner.invoke(app, ["connect", "foobar"])
    assert result.exit_code != 0
    assert "Unknown agent" in result.stdout or "unknown" in result.stdout.lower()


def test_connect_without_registration_bootstraps_guest(fake_home):
    """Connect without prior registration bootstraps a guest token."""
    with patch(
        "agentnet_cli.cli.core.connect.ensure_guest_credentials",
        return_value={
            "api_token": "ank1_guest",
            "platform_url": "https://x",
            "org_id": "org_guest",
            "agent_id": "agt_guest",
            "tier": "guest",
        },
    ), patch("agentnet_cli.cli.core.connect.detect_all", return_value=[]), patch(
        "agentnet_cli.cli.core.connect.get_connector"
    ) as get_connector:
        get_connector.return_value.detect.return_value = DetectionResult(
            agent_name="claude", detected=False
        )
        result = runner.invoke(app, ["connect", "claude"])
    assert result.exit_code == 0
    assert "not detected" in result.stdout.lower()


def test_dev_flag_sets_development_env(fake_home):
    with patch("agentnet_cli.cli.core.updater.maybe_auto_update"):
        runner.invoke(app, ["--dev", "detect"])
    assert os.environ.get("AGENTNET_ENV") == "development"


def test_setup_connects_before_optional_register(fake_home):
    """Setup bootstraps guest credentials, connects, then offers sign-in."""
    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={"api_token": "ank1_guest", "tier": "guest"},
    ) as ensure_guest, patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=[]
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ) as connect, patch(
        "agentnet_cli.cli.core.setup_wizard.register_command"
    ) as register, patch(
        "agentnet_cli.cli.core.setup_wizard.typer.confirm", return_value=False
    ):
        result = runner.invoke(app, ["setup", "--url", "http://localhost:8006"])

    assert result.exit_code == 0
    ensure_guest.assert_called_once_with(platform_url="http://localhost:8006")
    connect.assert_not_called()  # nothing detected
    register.assert_not_called()  # user declined optional sign-in
    assert "Guest API token ready" in result.stdout
    assert "Sign in" in result.stdout


def test_setup_can_skip_sign_in(fake_home):
    detections = [DetectionResult(agent_name="claude", detected=True)]
    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={"api_token": "ank1_guest", "tier": "guest"},
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=detections
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ) as connect, patch(
        "agentnet_cli.cli.core.setup_wizard.register_command"
    ) as register, patch(
        "agentnet_cli.cli.core.setup_wizard.typer.confirm", return_value=False
    ):
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    connect.assert_called_once_with(connect_all=True)
    register.assert_not_called()
    assert "Skipped" in result.stdout


def test_setup_guest_token_still_offers_sign_in(fake_home):
    """Existing guest credentials are kept; setup still offers optional login."""
    from agentnet_cli.infra.config import save_config

    save_config({
        "api_token": "ank1_guest",
        "platform_url": "https://x",
        "org_id": "org_guest",
        "agent_id": "agt_guest",
        "tier": "guest",
    })
    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={
            "api_token": "ank1_guest",
            "platform_url": "https://x",
            "tier": "guest",
        },
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=[]
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.register_command"
    ) as register, patch(
        "agentnet_cli.cli.core.setup_wizard.typer.confirm", return_value=True
    ):
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    register.assert_called_once()


def test_setup_connects_all_detected_agents_by_default(fake_home):
    from agentnet_cli.infra.config import save_config

    save_config({
        "api_token": "tok",
        "platform_url": "https://x",
        "org_id": "o",
        "agent_id": "a",
        "tier": "authenticated",
    })
    detections = [
        DetectionResult(agent_name="claude", detected=True),
        DetectionResult(agent_name="cursor", detected=False),
    ]

    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={
            "api_token": "tok",
            "platform_url": "https://x",
            "tier": "authenticated",
        },
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=detections
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ) as connect:
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    assert "Claude" in result.stdout
    connect.assert_called_once_with(connect_all=True)
    assert "Already signed in" in result.stdout


def test_setup_can_select_individual_detected_agent(fake_home):
    from agentnet_cli.infra.config import save_config

    save_config({
        "api_token": "tok",
        "platform_url": "https://x",
        "org_id": "o",
        "agent_id": "a",
        "tier": "authenticated",
    })
    detections = [
        DetectionResult(agent_name="claude", detected=True),
        DetectionResult(agent_name="cursor", detected=True),
    ]

    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={
            "api_token": "tok",
            "platform_url": "https://x",
            "tier": "authenticated",
        },
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=detections
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ) as connect:
        result = runner.invoke(app, ["setup", "--choose"], input="2\n1\n")

    assert result.exit_code == 0
    connect.assert_called_once_with(agent_name="claude")


def test_setup_individual_mode_defaults_to_no_agents(fake_home):
    from agentnet_cli.infra.config import save_config

    save_config({
        "api_token": "tok",
        "platform_url": "https://x",
        "org_id": "o",
        "agent_id": "a",
        "tier": "authenticated",
    })
    detections = [
        DetectionResult(agent_name="claude", detected=True),
        DetectionResult(agent_name="cursor", detected=True),
    ]

    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={"api_token": "tok", "tier": "authenticated"},
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=detections
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ) as connect:
        result = runner.invoke(app, ["setup", "--choose"], input="2\n\n")

    assert result.exit_code == 0
    assert "No agents configured" in result.stdout
    connect.assert_not_called()


def test_setup_can_skip_agent_configuration(fake_home):
    from agentnet_cli.infra.config import save_config

    save_config({
        "api_token": "tok",
        "platform_url": "https://x",
        "org_id": "o",
        "agent_id": "a",
        "tier": "authenticated",
    })
    detections = [DetectionResult(agent_name="claude", detected=True)]

    with patch(
        "agentnet_cli.cli.core.setup_wizard.ensure_guest_credentials",
        return_value={"api_token": "tok", "tier": "authenticated"},
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.detect_all", return_value=detections
    ), patch(
        "agentnet_cli.cli.core.setup_wizard.connect_command"
    ) as connect:
        result = runner.invoke(app, ["setup", "--choose"], input="3\n")

    assert result.exit_code == 0
    assert "No agents configured" in result.stdout
    connect.assert_not_called()


def test_setup_menu_drawer_resets_columns(monkeypatch):
    import io
    from agentnet_cli.cli.core import setup_wizard as setup

    output = io.StringIO()
    monkeypatch.setattr(setup.sys, "stdout", output)

    assert setup._draw_menu(["one", "two"], previous_line_count=2) == 2

    assert output.getvalue() == "\033[2F\r\r\033[2Kone\r\n\r\033[2Ktwo\r\n"


def test_setup_tui_enter_selects_highlighted_agent(monkeypatch):
    from agentnet_cli.cli.core import setup_wizard as setup

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
    from agentnet_cli.cli.core import setup_wizard as setup

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
    from agentnet_cli.cli.core import setup_wizard as setup

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


# ── auto-update: skipped on the critical-path hooks, kept for normal commands ──
def test_callback_skips_auto_update_on_hook_commands(fake_home, monkeypatch):
    # Hooks fire on the agent's critical path (prompt submit, each tool call, turn end), so the
    # callback must not run the possibly-blocking auto-update for them. The detached worker does.
    import sys as _sys

    with patch("agentnet_cli.cli.core.updater.maybe_auto_update") as mau:
        for argv in (["cursor-hook", "--peek"], ["skill-hook", "--post"], ["hermes-hook", "--pre"]):
            monkeypatch.setattr(_sys, "argv", ["agentnet", *argv])
            runner.invoke(app, argv, input="{}")
        mau.assert_not_called()


def test_callback_runs_auto_update_on_normal_command(fake_home, monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys, "argv", ["agentnet", "status"])
    with patch("agentnet_cli.cli.core.updater.maybe_auto_update") as mau:
        runner.invoke(app, ["status"])
        mau.assert_called_once()
