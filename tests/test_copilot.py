import json
from pathlib import Path
from agentnet_cli.agents.copilot import CopilotConnector


def _setup_copilot(home: Path) -> None:
    d = home / ".copilot"
    d.mkdir()
    (d / "config.json").write_text("{}")


def test_detect(fake_home):
    _setup_copilot(fake_home)
    assert CopilotConnector().detect().detected is True


def test_connect_creates_agent_md(fake_home):
    _setup_copilot(fake_home)
    result = CopilotConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success
    agent_md = fake_home / ".copilot" / "agents" / "agentnet.agent.md"
    assert agent_md.exists()
    assert "agentnet_discover" in agent_md.read_text()


def test_connect_writes_mcp_config(fake_home):
    _setup_copilot(fake_home)
    CopilotConnector().connect({"api_token": "t", "platform_url": "https://x"})
    mcp = fake_home / ".copilot" / "mcp-config.json"
    assert mcp.exists()
    data = json.loads(mcp.read_text())
    assert "agentnet" in data["mcpServers"]


def test_disconnect(fake_home):
    """Connect then disconnect — agent.md and MCP entry removed."""
    _setup_copilot(fake_home)
    connector = CopilotConnector()
    result = connector.connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success

    manifest_entry = {
        "mcp_registered": result.mcp_entry,
        "files_created": [str(p) for p in result.files_created],
    }

    ok = connector.disconnect(manifest_entry)
    assert ok

    agent_md = fake_home / ".copilot" / "agents" / "agentnet.agent.md"
    assert not agent_md.exists()

    mcp_path = fake_home / ".copilot" / "mcp-config.json"
    if mcp_path.exists():
        data = json.loads(mcp_path.read_text())
        assert "agentnet" not in data.get("mcpServers", {})


def test_disconnect_removes_empty_dirs(fake_home):
    """After disconnect, empty agents/ directory is cleaned up."""
    _setup_copilot(fake_home)
    connector = CopilotConnector()
    result = connector.connect({"api_token": "t", "platform_url": "https://x"})

    manifest_entry = {
        "mcp_registered": result.mcp_entry,
        "files_created": [str(p) for p in result.files_created],
    }

    connector.disconnect(manifest_entry)

    agents_dir = fake_home / ".copilot" / "agents"
    assert not agents_dir.exists(), "Empty agents/ dir should be removed"
