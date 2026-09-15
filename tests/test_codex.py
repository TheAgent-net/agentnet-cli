from pathlib import Path
from agentnet_cli.connectors.codex import CodexConnector


def _setup_codex(home: Path) -> None:
    d = home / ".codex"
    d.mkdir()
    (d / "config.toml").write_text("")


def test_detect(fake_home):
    _setup_codex(fake_home)
    assert CodexConnector().detect().detected is True


def test_connect_creates_skill(fake_home):
    _setup_codex(fake_home)
    result = CodexConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success
    skill = fake_home / ".codex" / "skills" / "agentnet" / "SKILL.md"
    assert skill.exists()
    skill_content = skill.read_text()
    assert "agentnet_search" in skill_content
    assert "COMPOSIO_SEARCH_TOOLS" in skill_content


def test_connect_appends_toml(fake_home):
    _setup_codex(fake_home)
    result = CodexConnector().connect({"api_token": "t", "platform_url": "https://x"})
    toml_content = (fake_home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.agentnet]" in toml_content
    assert "default_tools_approval_mode" in toml_content
    assert "[mcp_servers.composio]" in toml_content
    assert "https://connect.composio.dev/mcp" in toml_content
    assert result.mcp_entry["composio"]["owned"] is True


def test_disconnect_removes_owned_composio(fake_home):
    _setup_codex(fake_home)
    connector = CodexConnector()
    result = connector.connect({"api_token": "t", "platform_url": "https://x"})
    connector.disconnect({
        "files_created": [str(p) for p in result.files_created],
        "mcp_registered": result.mcp_entry,
    })
    toml_content = (fake_home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.agentnet]" not in toml_content
    assert "[mcp_servers.composio]" not in toml_content
    assert "connect.composio.dev" not in toml_content
