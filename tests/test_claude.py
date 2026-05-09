import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from agentnet_cli.agents.claude import ClaudeConnector

_PLUGIN_ID = "agentnet@agentnet-cli"


def _setup_claude(home: Path) -> None:
    d = home / ".claude"
    d.mkdir()
    (d / "settings.json").write_text("{}")


def _mock_run_ok(*args, **kwargs):
    return MagicMock(returncode=0, stderr=b"")


# --- detect (unchanged logic) ---


def test_detect_found(fake_home):
    _setup_claude(fake_home)
    r = ClaudeConnector().detect()
    assert r.detected is True
    assert r.config_root == fake_home / ".claude"


def test_detect_not_found(fake_home):
    r = ClaudeConnector().detect()
    assert r.detected is False


# --- connect ---


def test_connect_calls_marketplace_add(fake_home):
    _setup_claude(fake_home)
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=_mock_run_ok) as mock_run:
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success
    marketplace_calls = [c for c in mock_run.call_args_list if "marketplace" in c[0][0]]
    assert len(marketplace_calls) == 1
    cmd = marketplace_calls[0][0][0]
    assert cmd[:4] == ["claude", "plugin", "marketplace", "add"]


def test_connect_calls_plugin_install(fake_home):
    _setup_claude(fake_home)
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=_mock_run_ok) as mock_run:
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success
    mock_run.assert_any_call(
        ["claude", "plugin", "install", _PLUGIN_ID, "--scope", "user"],
        capture_output=True,
        timeout=120,
    )


def test_connect_no_claude_binary(fake_home):
    _setup_claude(fake_home)
    with patch("shutil.which", return_value=None):
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success is False
    assert any("Claude Code" in e for e in result.errors)


def test_connect_install_failure(fake_home):
    _setup_claude(fake_home)
    fail = MagicMock(returncode=1, stderr=b"network error")

    def side_effect(cmd, **kw):
        if "install" in cmd:
            return fail
        return MagicMock(returncode=0, stderr=b"")

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=side_effect):
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success is False
    assert any("network error" in e for e in result.errors)


def test_connect_cleans_legacy_skill(fake_home):
    _setup_claude(fake_home)
    skill_dir = fake_home / ".claude" / "skills" / "agentnet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("old")

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=_mock_run_ok):
        ClaudeConnector().connect({"api_token": "t"})

    assert not (skill_dir / "SKILL.md").exists()


def test_connect_cleans_legacy_mcp(fake_home):
    _setup_claude(fake_home)
    claude_json = fake_home / ".claude.json"
    claude_json.write_text(json.dumps({
        "mcpServers": {"agentnet": {"command": "uvx"}, "other": {"command": "x"}},
    }))

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=_mock_run_ok):
        ClaudeConnector().connect({"api_token": "t"})

    data = json.loads(claude_json.read_text())
    assert "agentnet" not in data["mcpServers"]
    assert "other" in data["mcpServers"]


def test_connect_cleans_legacy_permissions(fake_home):
    _setup_claude(fake_home)
    settings = fake_home / ".claude" / "settings.json"
    settings.write_text(json.dumps({
        "permissions": {"allow": ["mcp__agentnet__*", "other_rule"]},
    }))

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=_mock_run_ok):
        ClaudeConnector().connect({"api_token": "t"})

    data = json.loads(settings.read_text())
    assert "mcp__agentnet__*" not in data["permissions"]["allow"]
    assert "other_rule" in data["permissions"]["allow"]


# --- disconnect ---


def test_disconnect_calls_plugin_uninstall(fake_home):
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", side_effect=_mock_run_ok) as mock_run:
        ok = ClaudeConnector().disconnect({})
    assert ok
    mock_run.assert_called_once_with(
        ["claude", "plugin", "uninstall", _PLUGIN_ID, "--scope", "user", "-y"],
        capture_output=True,
        timeout=120,
    )


def test_disconnect_no_claude_binary(fake_home):
    with patch("shutil.which", return_value=None):
        ok = ClaudeConnector().disconnect({})
    assert ok
