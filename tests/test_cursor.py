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
    assert "composio:*" not in perms.read_text()


def test_connect_creates_subagent(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    agent_md = fake_home / ".cursor" / "agents" / "agentnet.md"
    assert agent_md.exists()


def test_connect_writes_mcp_json(fake_home):
    _setup_cursor(fake_home)
    result = CursorConnector().connect(
        {"api_token": "agn_test", "platform_url": "https://test.agentnet.market"},
    )
    mcp_path = fake_home / ".cursor" / "mcp.json"
    assert mcp_path.exists()
    data = json.loads(mcp_path.read_text())
    assert "agentnet" in data["mcpServers"]
    assert data["mcpServers"]["composio"] == {"url": "https://connect.composio.dev/mcp"}
    assert result.mcp_entry["composio"]["owned"] is True
    assert "command" in data["mcpServers"]["agentnet"]


def test_connect_skips_composio_when_disabled(fake_home, monkeypatch):
    monkeypatch.setenv("AGENTNET_COMPOSIO_MCP", "0")
    _setup_cursor(fake_home)
    CursorConnector().connect(
        {"api_token": "agn_test", "platform_url": "https://test.agentnet.market"},
    )
    data = json.loads((fake_home / ".cursor" / "mcp.json").read_text())
    assert "agentnet" in data["mcpServers"]
    assert "composio" not in data["mcpServers"]


def test_connect_skips_existing_composio(fake_home):
    _setup_cursor(fake_home)
    mcp_path = fake_home / ".cursor" / "mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {"composio": {"url": "https://example.invalid/mcp"}},
    }))
    result = CursorConnector().connect(
        {"api_token": "agn_test", "platform_url": "https://test.agentnet.market"},
    )
    data = json.loads(mcp_path.read_text())
    assert data["mcpServers"]["composio"]["url"] == "https://example.invalid/mcp"
    assert "agentnet" in data["mcpServers"]
    assert result.mcp_entry["composio"]["owned"] is False


def test_disconnect_preserves_user_composio(fake_home):
    _setup_cursor(fake_home)
    mcp_path = fake_home / ".cursor" / "mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {"composio": {"url": "https://example.invalid/mcp"}},
    }))
    c = CursorConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    c.disconnect({
        "files_created": [str(p) for p in result.files_created],
        "files_modified": [],
        "mcp_registered": result.mcp_entry,
    })
    data = json.loads(mcp_path.read_text())
    assert "agentnet" not in data.get("mcpServers", {})
    assert data["mcpServers"]["composio"]["url"] == "https://example.invalid/mcp"


def test_disconnect_removes_owned_composio(fake_home):
    _setup_cursor(fake_home)
    c = CursorConnector()
    result = c.connect({"api_token": "agn_test", "platform_url": "https://test.agentnet.market"})
    manifest = {
        "files_created": [str(p) for p in result.files_created],
        "files_modified": [],
        "mcp_registered": result.mcp_entry,
    }
    c.disconnect(manifest)
    data = json.loads((fake_home / ".cursor" / "mcp.json").read_text())
    assert "agentnet" not in data.get("mcpServers", {})
    assert "composio" not in data.get("mcpServers", {})


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
