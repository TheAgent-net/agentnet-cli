import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from agentnet_cli.connectors.claude import ClaudeConnector

_PLUGIN_ID = "agentnet@agentnet-cli"


def _setup_claude(home: Path) -> None:
    d = home / ".claude"
    d.mkdir()
    (d / "settings.json").write_text("{}")


def _mock_run_ok(*args, **kwargs):
    return MagicMock(returncode=0, stderr=b"")


def _patch_claude_ok():
    return (
        patch("agentnet_cli.connectors.claude.find_executable", return_value="/usr/bin/claude"),
        patch("agentnet_cli.connectors.claude.run_tool", side_effect=_mock_run_ok),
    )


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
    calls: list[list[str]] = []

    def _capture(name, args, **kw):
        calls.append([name, *args])
        return _mock_run_ok()

    with patch("agentnet_cli.connectors.claude.find_executable", return_value="/usr/bin/claude"), \
         patch("agentnet_cli.connectors.claude.run_tool", side_effect=_capture):
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success
    marketplace_calls = [c for c in calls if "marketplace" in c]
    assert len(marketplace_calls) == 1
    assert marketplace_calls[0][:4] == ["claude", "plugin", "marketplace", "add"]


def test_connect_calls_plugin_install(fake_home):
    _setup_claude(fake_home)
    calls: list[list[str]] = []

    def _capture(name, args, **kw):
        calls.append([name, *args])
        return _mock_run_ok()

    with patch("agentnet_cli.connectors.claude.find_executable", return_value="/usr/bin/claude"), \
         patch("agentnet_cli.connectors.claude.run_tool", side_effect=_capture):
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success
    assert ["claude", "plugin", "install", _PLUGIN_ID, "--scope", "user"] in calls


def test_connect_no_claude_binary(fake_home):
    _setup_claude(fake_home)
    with patch("agentnet_cli.connectors.claude.find_executable", return_value=None):
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success is False
    assert any("Claude Code" in e for e in result.errors)


def test_connect_installs_search_hook(fake_home):
    """connect writes the AgentNet every-prompt hook into settings.json."""
    _setup_claude(fake_home)
    p_res, p_run = _patch_claude_ok()
    with p_res, p_run:
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success
    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    pre = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    peek = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    post = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "skill-hook --pre" in pre
    assert "skill-hook --peek" in peek
    assert "skill-hook --post" in post


def test_connect_marketplace_add_has_no_scope(fake_home):
    """`marketplace add` must not receive --scope (errors on some CC versions)."""
    _setup_claude(fake_home)
    calls: list[list[str]] = []

    def _capture(name, args, **kw):
        calls.append([name, *args])
        return _mock_run_ok()

    with patch("agentnet_cli.connectors.claude.find_executable", return_value="/usr/bin/claude"), \
         patch("agentnet_cli.connectors.claude.run_tool", side_effect=_capture):
        ClaudeConnector().connect({"api_token": "t"})
    add = next(c for c in calls if "marketplace" in c)
    assert "--scope" not in add


def test_connect_plugin_failure_is_nonfatal(fake_home):
    """Plugin (discovery tools) failure no longer fails connect — the hook is still installed."""
    _setup_claude(fake_home)
    fail = MagicMock(returncode=1, stderr=b"network error")

    def side_effect(name, args, **kw):
        if "install" in args:
            return fail
        return MagicMock(returncode=0, stderr=b"")

    with patch("agentnet_cli.connectors.claude.find_executable", return_value="/usr/bin/claude"), \
         patch("agentnet_cli.connectors.claude.run_tool", side_effect=side_effect):
        result = ClaudeConnector().connect({"api_token": "t"})
    assert result.success is True
    assert any("network error" in e for e in result.errors)
    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    assert "skill-hook --post" in settings["hooks"]["Stop"][0]["hooks"][0]["command"]


def test_connect_cleans_legacy_skill(fake_home):
    _setup_claude(fake_home)
    skill_dir = fake_home / ".claude" / "skills" / "agentnet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("old")

    p_res, p_run = _patch_claude_ok()
    with p_res, p_run:
        ClaudeConnector().connect({"api_token": "t"})

    assert not (skill_dir / "SKILL.md").exists()


def test_connect_cleans_legacy_mcp(fake_home):
    _setup_claude(fake_home)
    claude_json = fake_home / ".claude.json"
    claude_json.write_text(json.dumps({
        "mcpServers": {"agentnet": {"command": "uvx"}, "other": {"command": "x"}},
    }))

    p_res, p_run = _patch_claude_ok()
    with p_res, p_run:
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

    p_res, p_run = _patch_claude_ok()
    with p_res, p_run:
        ClaudeConnector().connect({"api_token": "t"})

    data = json.loads(settings.read_text())
    assert "mcp__agentnet__*" not in data["permissions"]["allow"]
    assert "other_rule" in data["permissions"]["allow"]


def test_connect_mirrored_windows_writes_hooks(windows_env, fake_home):
    """Mirrored Windows env gets settings hooks; plugin step is skipped with a note."""
    root = windows_env.home / "AppData" / "Roaming" / "Claude"
    root.mkdir(parents=True)
    (root / "settings.json").write_text("{}", encoding="utf-8")
    result = ClaudeConnector(windows_env).connect({"api_token": "t"})
    assert result.success
    assert any("plugin marketplace step skipped" in e for e in result.errors)
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    assert "skill-hook --pre" in settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]


# --- disconnect ---


def test_disconnect_calls_plugin_uninstall(fake_home):
    calls: list[list[str]] = []

    def _capture(name, args, **kw):
        calls.append([name, *args])
        return _mock_run_ok()

    with patch("agentnet_cli.connectors.claude.run_tool", side_effect=_capture):
        ok = ClaudeConnector().disconnect({})
    assert ok
    assert ["claude", "plugin", "uninstall", _PLUGIN_ID, "--scope", "user", "-y"] in calls


def test_disconnect_no_claude_binary(fake_home):
    with patch("agentnet_cli.connectors.claude.run_tool", return_value=None):
        ok = ClaudeConnector().disconnect({})
    assert ok
