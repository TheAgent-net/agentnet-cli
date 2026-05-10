import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from agentnet_cli.agents.openclaw import OpenClawConnector

_PLUGIN_ID = "agentnet"


def _setup_openclaw(home: Path) -> None:
    d = home / ".openclaw"
    d.mkdir()
    (d / "openclaw.json").write_text("{}")


def _mock_run_ok(*args, **kwargs):
    return MagicMock(returncode=0, stderr=b"")


# --- detect ---


def test_detect_found(fake_home):
    _setup_openclaw(fake_home)
    r = OpenClawConnector().detect()
    assert r.detected is True
    assert r.config_root == fake_home / ".openclaw"


def test_detect_not_found(fake_home):
    r = OpenClawConnector().detect()
    assert r.detected is False


# --- connect ---


def test_connect_calls_plugin_install(fake_home):
    _setup_openclaw(fake_home)
    with patch("shutil.which", return_value="/usr/bin/openclaw"), \
         patch("subprocess.run", side_effect=_mock_run_ok) as mock_run:
        result = OpenClawConnector().connect({"api_token": "t"})
    assert result.success
    install_calls = [c for c in mock_run.call_args_list if "install" in c[0][0]]
    assert len(install_calls) == 1
    cmd = install_calls[0][0][0]
    assert cmd[:3] == ["openclaw", "plugins", "install"]
    assert "--force" in cmd


def test_connect_no_openclaw_binary(fake_home):
    _setup_openclaw(fake_home)
    with patch("shutil.which", return_value=None):
        result = OpenClawConnector().connect({"api_token": "t"})
    assert result.success is False
    assert any("OpenClaw" in e for e in result.errors)


def test_connect_install_failure(fake_home):
    _setup_openclaw(fake_home)
    fail = MagicMock(returncode=1, stderr=b"network error")

    with patch("shutil.which", return_value="/usr/bin/openclaw"), \
         patch("subprocess.run", return_value=fail):
        result = OpenClawConnector().connect({"api_token": "t"})
    assert result.success is False
    assert any("network error" in e for e in result.errors)


def test_connect_cleans_legacy_plugin_entry(fake_home):
    _setup_openclaw(fake_home)
    config = fake_home / ".openclaw" / "openclaw.json"
    config.write_text(json.dumps({
        "plugins": {"agentnet-gateway": {"enabled": True}, "other": {"enabled": True}},
    }))

    with patch("shutil.which", return_value="/usr/bin/openclaw"), \
         patch("subprocess.run", side_effect=_mock_run_ok):
        OpenClawConnector().connect({"api_token": "t"})

    data = json.loads(config.read_text())
    assert "agentnet-gateway" not in data["plugins"]
    assert "other" in data["plugins"]


def test_connect_cleans_legacy_backup(fake_home):
    _setup_openclaw(fake_home)
    backup = fake_home / ".agentnet" / "backups" / "openclaw" / "openclaw.json.bak"
    backup.parent.mkdir(parents=True)
    backup.write_text("{}")

    with patch("shutil.which", return_value="/usr/bin/openclaw"), \
         patch("subprocess.run", side_effect=_mock_run_ok):
        OpenClawConnector().connect({"api_token": "t"})

    assert not backup.exists()


# --- disconnect ---


def test_disconnect_calls_plugin_uninstall(fake_home):
    with patch("shutil.which", return_value="/usr/bin/openclaw"), \
         patch("subprocess.run", side_effect=_mock_run_ok) as mock_run:
        ok = OpenClawConnector().disconnect({})
    assert ok
    mock_run.assert_called_once_with(
        ["openclaw", "plugins", "uninstall", _PLUGIN_ID, "--force"],
        capture_output=True,
        timeout=120,
    )


def test_disconnect_no_openclaw_binary(fake_home):
    with patch("shutil.which", return_value=None):
        ok = OpenClawConnector().disconnect({})
    assert ok
