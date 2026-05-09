import json
from pathlib import Path
from agentnet_cli.agents.claude import ClaudeConnector


def _setup_claude(home: Path) -> None:
    d = home / ".claude"
    d.mkdir()
    (d / "settings.json").write_text("{}")


def test_detect_found(fake_home):
    _setup_claude(fake_home)
    c = ClaudeConnector()
    r = c.detect()
    assert r.detected is True
    assert r.config_root == fake_home / ".claude"


def test_detect_not_found(fake_home):
    c = ClaudeConnector()
    r = c.detect()
    assert r.detected is False


def test_connect_creates_skill(fake_home):
    _setup_claude(fake_home)
    c = ClaudeConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    assert result.success
    skill_path = fake_home / ".claude" / "skills" / "agentnet" / "SKILL.md"
    assert skill_path.exists()
    content = skill_path.read_text()
    assert "agentnet_discover" in content


def test_connect_writes_mcp_to_claude_json(fake_home):
    _setup_claude(fake_home)
    claude_json = fake_home / ".claude.json"
    claude_json.write_text("{}")
    c = ClaudeConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    assert result.success
    data = json.loads(claude_json.read_text())
    assert "agentnet" in data.get("mcpServers", {})


def test_connect_merges_existing_mcp(fake_home):
    _setup_claude(fake_home)
    claude_json = fake_home / ".claude.json"
    claude_json.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    c = ClaudeConnector()
    c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    data = json.loads(claude_json.read_text())
    assert "other" in data["mcpServers"]
    assert "agentnet" in data["mcpServers"]


def test_disconnect_removes_files(fake_home):
    _setup_claude(fake_home)
    c = ClaudeConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    manifest_entry = {
        "files_created": [str(p) for p in result.files_created],
        "files_modified": [],
        "mcp_registered": result.mcp_entry,
    }
    ok = c.disconnect(manifest_entry)
    assert ok
    skill_path = fake_home / ".claude" / "skills" / "agentnet" / "SKILL.md"
    assert not skill_path.exists()
