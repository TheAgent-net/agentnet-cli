"""Tests for updater.py — stale-connection refresh, PyPI version check, upgrade command."""

import sys
from unittest.mock import MagicMock, patch

from agentnet_cli.config import save_config
from agentnet_cli.manifest import save_manifest
from agentnet_cli.updater import _upgrade_command, check_pypi_latest, refresh_stale_connections


def test_refresh_no_config(fake_home):
    """No config.json — returns 0 without errors."""
    assert refresh_stale_connections() == 0


def test_refresh_no_connections(fake_home):
    """Config exists but manifest has no connections — returns 0."""
    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    assert refresh_stale_connections() == 0


def test_refresh_versions_match(fake_home):
    """All connections already at current CLI version — nothing refreshed."""
    from agentnet_cli import __version__

    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    save_manifest(
        {
            "connections": {
                "claude": {"cli_version": __version__, "files_created": []},
            }
        }
    )
    assert refresh_stale_connections() == 0


@patch("agentnet_cli.updater.get_connector")
def test_refresh_stale_connection(mock_get_connector, fake_home):
    """Old cli_version + agent detected => connect() called, returns 1."""
    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    save_manifest(
        {
            "connections": {
                "claude": {"cli_version": "0.0.0-old", "files_created": []},
            }
        }
    )

    mock_connector = MagicMock()
    mock_connector.detect.return_value = MagicMock(detected=True)
    mock_connector.connect.return_value = MagicMock(
        success=True, files_created=[], files_modified=[], mcp_entry={}
    )
    mock_get_connector.return_value = mock_connector

    assert refresh_stale_connections() == 1
    mock_connector.connect.assert_called_once()


@patch("agentnet_cli.updater.get_connector")
def test_refresh_stale_undetected(mock_get_connector, fake_home):
    """Old version but agent not detected — skip, returns 0."""
    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    save_manifest(
        {
            "connections": {
                "claude": {"cli_version": "0.0.0-old", "files_created": []},
            }
        }
    )

    mock_connector = MagicMock()
    mock_connector.detect.return_value = MagicMock(detected=False)
    mock_get_connector.return_value = mock_connector

    assert refresh_stale_connections() == 0
    mock_connector.connect.assert_not_called()


@patch("agentnet_cli.updater.get_connector")
def test_refresh_connect_error(mock_get_connector, fake_home):
    """connect() raises OSError — logged, skipped, returns 0."""
    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    save_manifest(
        {
            "connections": {
                "claude": {"cli_version": "0.0.0-old", "files_created": []},
            }
        }
    )

    mock_connector = MagicMock()
    mock_connector.detect.return_value = MagicMock(detected=True)
    mock_connector.connect.side_effect = OSError("disk full")
    mock_get_connector.return_value = mock_connector

    # Should not raise
    assert refresh_stale_connections() == 0


@patch("httpx.get")
def test_check_pypi_latest_success(mock_get):
    """Successful PyPI lookup returns version string."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"info": {"version": "1.2.3"}}
    mock_get.return_value = mock_resp

    assert check_pypi_latest() == "1.2.3"


@patch("httpx.get")
def test_check_pypi_latest_failure(mock_get):
    """PyPI unreachable — returns None."""
    mock_get.side_effect = Exception("timeout")

    assert check_pypi_latest() is None


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_uv_tool(mock_which, mock_run):
    """uv detected and agentnet-cli in tool list => uv tool upgrade."""
    mock_which.side_effect = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None
    mock_run.return_value = MagicMock(stdout="agentnet-cli v0.1.0\nother-tool v2.0\n", returncode=0)

    cmd = _upgrade_command()
    assert cmd == ["uv", "tool", "upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_uv_no_false_positive(mock_which, mock_run):
    """uv tool list has 'my-agentnet-cli-fork' — should NOT match."""
    mock_which.side_effect = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None
    mock_run.return_value = MagicMock(stdout="my-agentnet-cli-fork v1.0\n", returncode=0)

    cmd = _upgrade_command()
    assert cmd == [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_pipx(mock_which, mock_run):
    """pipx detected => pipx upgrade."""
    mock_which.side_effect = lambda cmd: "/usr/bin/pipx" if cmd == "pipx" else None
    mock_run.return_value = MagicMock(stdout="agentnet-cli 0.1.0\n", returncode=0)

    cmd = _upgrade_command()
    assert cmd == ["pipx", "upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_pip_fallback(mock_which, mock_run):
    """No uv or pipx — falls back to pip."""
    mock_which.return_value = None
    cmd = _upgrade_command()
    assert cmd == [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.get_connector")
def test_refresh_stale_quiet_suppresses_output(mock_get_connector, fake_home, capsys):
    """quiet=True with refreshed > 0 prints nothing."""
    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    save_manifest(
        {
            "connections": {
                "claude": {"cli_version": "0.0.0-old", "files_created": []},
            }
        }
    )

    mock_connector = MagicMock()
    mock_connector.detect.return_value = MagicMock(detected=True)
    mock_connector.connect.return_value = MagicMock(
        success=True, files_created=[], files_modified=[], mcp_entry={}
    )
    mock_get_connector.return_value = mock_connector

    assert refresh_stale_connections(quiet=True) == 1
    captured = capsys.readouterr()
    assert "Refreshed" not in captured.out
    assert "Refreshed" not in captured.err


@patch("agentnet_cli.updater.get_connector")
def test_refresh_connect_returns_failure(mock_get_connector, fake_home, capsys):
    """connect() returns success=False — logs warning, does not count as refreshed."""
    save_config({"api_token": "tok", "org_id": "o", "agent_id": "a"})
    save_manifest(
        {
            "connections": {
                "claude": {"cli_version": "0.0.0-old", "files_created": []},
            }
        }
    )

    mock_connector = MagicMock()
    mock_connector.detect.return_value = MagicMock(detected=True)
    mock_connector.connect.return_value = MagicMock(success=False)
    mock_get_connector.return_value = mock_connector

    assert refresh_stale_connections() == 0


@patch("agentnet_cli.updater.check_pypi_latest", return_value="9.9.9")
@patch("agentnet_cli.updater._upgrade_command", return_value=["echo", "ok"])
@patch("agentnet_cli.updater.subprocess.run")
def test_self_upgrade_success(mock_run, mock_cmd, mock_pypi):
    """Successful upgrade returns (True, version)."""
    from agentnet_cli.updater import self_upgrade

    mock_run.return_value = MagicMock(returncode=0)
    ok, msg = self_upgrade()
    assert ok is True
    assert msg == "9.9.9"


@patch("agentnet_cli.updater._upgrade_command", return_value=["false"])
@patch("agentnet_cli.updater.subprocess.run")
def test_self_upgrade_failure(mock_run, mock_cmd):
    """Failed upgrade returns (False, stderr snippet)."""
    from agentnet_cli.updater import self_upgrade

    mock_run.return_value = MagicMock(returncode=1, stderr="ERROR: no matching distribution")
    ok, msg = self_upgrade()
    assert ok is False
    assert "no matching distribution" in msg


@patch("agentnet_cli.updater._upgrade_command", return_value=["false"])
@patch("agentnet_cli.updater.subprocess.run", side_effect=OSError("command not found"))
def test_self_upgrade_exception(mock_run, mock_cmd):
    """subprocess raises — returns (False, error string)."""
    from agentnet_cli.updater import self_upgrade

    ok, msg = self_upgrade()
    assert ok is False
    assert "command not found" in msg


@patch("agentnet_cli.updater.subprocess.run", side_effect=Exception("timeout"))
@patch("agentnet_cli.updater.shutil.which", return_value="/usr/bin/uv")
def test_upgrade_command_uv_subprocess_error(mock_which, mock_run):
    """uv exists but subprocess fails — falls through to pip."""
    cmd = _upgrade_command()
    assert cmd == [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_uv_not_in_tool_list(mock_which, mock_run):
    """uv exists but agentnet-cli not in tool list — tries pipx then pip."""
    mock_which.side_effect = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None
    mock_run.return_value = MagicMock(stdout="other-tool 1.0.0\n", returncode=0)
    cmd = _upgrade_command()
    assert cmd == [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_pipx_subprocess_error(mock_which, mock_run):
    """pipx exists but subprocess fails — falls through to pip."""
    mock_which.side_effect = lambda cmd: "/usr/bin/pipx" if cmd == "pipx" else None
    mock_run.side_effect = Exception("timeout")
    cmd = _upgrade_command()
    assert cmd == [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]


@patch("agentnet_cli.updater.subprocess.run")
@patch("agentnet_cli.updater.shutil.which")
def test_upgrade_command_pipx_not_in_list(mock_which, mock_run):
    """pipx exists but agentnet-cli not installed via pipx — falls to pip."""
    mock_which.side_effect = lambda cmd: "/usr/bin/pipx" if cmd == "pipx" else None
    mock_run.return_value = MagicMock(stdout="other-tool 1.0.0\n", returncode=0)
    cmd = _upgrade_command()
    assert cmd == [sys.executable, "-m", "pip", "install", "--upgrade", "agentnet-cli"]
