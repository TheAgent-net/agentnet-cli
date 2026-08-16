import json
from pathlib import Path
from agentnet_cli.connectors.cursor import CursorConnector


def _setup_cursor(home: Path) -> None:
    d = home / ".cursor"
    (d / "extensions").mkdir(parents=True)


def test_detect_found(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    r = c.detect()
    assert r.detected is True


def test_detect_not_found(fake_home):
    c = CursorConnector()
    assert c.detect().detected is False


def test_connect_creates_mdc_rule(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    assert result.success
    mdc = fake_home / ".cursor" / "rules" / "agentnet.mdc"
    assert mdc.exists()
    assert "agentnet_search" in mdc.read_text()
    perms = fake_home / ".cursor" / "permissions.json"
    assert perms.exists()
    assert "agentnet:*" in perms.read_text()


def test_connect_creates_subagent(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    agent_md = fake_home / ".cursor" / "agents" / "agentnet.md"
    assert agent_md.exists()


def test_connect_writes_mcp_json(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    mcp_path = fake_home / ".cursor" / "mcp.json"
    assert mcp_path.exists()
    data = json.loads(mcp_path.read_text())
    assert "agentnet" in data["mcpServers"]


def test_connect_installs_local_plugin(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    plugin_dir = fake_home / ".cursor" / "plugins" / "local" / "agentnet"
    assert plugin_dir.is_dir()
    assert (plugin_dir / ".cursor-plugin" / "plugin.json").is_file()
    assert (plugin_dir / "hooks" / "hooks.json").is_file()
    assert (plugin_dir / "mcp.json").is_file()
    assert (plugin_dir / "skills" / "agentnet" / "SKILL.md").is_file()
    assert (plugin_dir / "rules" / "agentnet.mdc").is_file()
    assert (plugin_dir / "agents" / "agentnet.md").is_file()
    assert result.mcp_entry["plugin_dir"] == str(plugin_dir)
    hooks = json.loads((plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert "beforeSubmitPrompt" in hooks["hooks"]
    assert "preToolUse" in hooks["hooks"]
    assert "stop" in hooks["hooks"]


def test_disconnect_removes_all(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    manifest = {
        "files_created": [str(p) for p in result.files_created],
        "files_modified": [],
        "mcp_registered": result.mcp_entry,
    }
    c.disconnect(manifest)
    assert not (fake_home / ".cursor" / "rules" / "agentnet.mdc").exists()
    assert not (fake_home / ".cursor" / "agents" / "agentnet.md").exists()
    assert not (fake_home / ".cursor" / "plugins" / "local" / "agentnet").exists()


def test_connect_mirrored_windows_env(windows_env):
    """Cursor connector writes into a fake Windows home via Environment."""
    cursor_root = windows_env.home / ".cursor"
    (cursor_root / "extensions").mkdir(parents=True)
    c = CursorConnector(windows_env)
    assert c.detect().detected is True
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    assert result.success
    mcp = json.loads((cursor_root / "mcp.json").read_text(encoding="utf-8"))
    # Bridged env uses wsl.exe (or native windows agentnet), never uvx.
    assert mcp["mcpServers"]["agentnet"]["command"] != "uvx"
    assert (cursor_root / "rules" / "agentnet.mdc").exists()
