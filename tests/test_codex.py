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


def test_connect_appends_toml(fake_home):
    _setup_codex(fake_home)
    CodexConnector().connect({"api_token": "t", "platform_url": "https://x"})
    toml_content = (fake_home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.agentnet]" in toml_content
    assert "default_tools_approval_mode" in toml_content


def test_connect_mirrored_windows_env(windows_env):
    root = windows_env.home / ".codex"
    root.mkdir(parents=True)
    (root / "config.toml").write_text("", encoding="utf-8")
    c = CodexConnector(windows_env)
    result = c.connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success
    toml_content = (root / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.agentnet]" in toml_content
    assert "uvx" not in toml_content
