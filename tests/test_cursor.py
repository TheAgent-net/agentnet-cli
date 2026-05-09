import json
from pathlib import Path
from agentnet_cli.agents.cursor import CursorConnector


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
    assert "agentnet_discover" in mdc.read_text()


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
