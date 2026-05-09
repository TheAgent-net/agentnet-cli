from pathlib import Path

import yaml

from agentnet_cli.agents.hermes import HermesConnector


def _setup_hermes(home: Path) -> None:
    d = home / ".hermes"
    d.mkdir()
    (d / "config.yaml").write_text("model:\n  provider: openai\n")


def test_detect(fake_home):
    _setup_hermes(fake_home)
    assert HermesConnector().detect().detected is True


def test_detect_no_hermes(fake_home):
    assert HermesConnector().detect().detected is False


def test_connect_creates_plugin_dir(fake_home):
    _setup_hermes(fake_home)
    result = HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success

    plugin_dir = fake_home / ".hermes" / "plugins" / "agentnet"
    assert plugin_dir.is_dir()
    assert (plugin_dir / "plugin.yaml").exists()
    assert (plugin_dir / "__init__.py").exists()
    assert (plugin_dir / "schemas.py").exists()
    assert (plugin_dir / "handlers.py").exists()
    assert (plugin_dir / "skills" / "agentnet" / "SKILL.md").exists()


def test_connect_enables_plugin(fake_home):
    _setup_hermes(fake_home)
    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    assert "agentnet" in data.get("plugins", {}).get("enabled", [])


def test_connect_preserves_existing_config(fake_home):
    _setup_hermes(fake_home)
    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    assert data["model"]["provider"] == "openai"


def test_connect_idempotent(fake_home):
    _setup_hermes(fake_home)
    connector = HermesConnector()
    connector.connect({"api_token": "t", "platform_url": "https://x"})
    connector.connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    enabled = data.get("plugins", {}).get("enabled", [])
    assert enabled.count("agentnet") == 1


def test_connect_returns_plugin_mcp_entry(fake_home):
    _setup_hermes(fake_home)
    result = HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.mcp_entry["scope"] == "plugin"
    assert "plugin_dir" in result.mcp_entry


def test_disconnect(fake_home):
    _setup_hermes(fake_home)
    connector = HermesConnector()
    result = connector.connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success

    manifest_entry = {
        "mcp_registered": result.mcp_entry,
        "files_created": [str(p) for p in result.files_created],
    }

    ok = connector.disconnect(manifest_entry)
    assert ok

    plugin_dir = fake_home / ".hermes" / "plugins" / "agentnet"
    assert not plugin_dir.exists()

    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text()) or {}
    enabled = data.get("plugins", {}).get("enabled", [])
    assert "agentnet" not in enabled


def test_connect_cleans_legacy_mcp_servers(fake_home):
    """If old YAML-surgery entries exist, connect() removes them."""
    d = fake_home / ".hermes"
    d.mkdir()
    legacy_config = {
        "model": {"provider": "openai"},
        "mcp_servers": {"agentnet": {"command": "uvx", "args": ["agentnet-cli", "mcp-serve"]}},
        "platform_toolsets": {"cli": ["hermes-cli", "mcp-agentnet"]},
    }
    (d / "config.yaml").write_text(yaml.dump(legacy_config))

    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((d / "config.yaml").read_text())
    assert "agentnet" not in data.get("mcp_servers", {})
    for toolsets in data.get("platform_toolsets", {}).values():
        assert "mcp-agentnet" not in toolsets


def test_connect_installs_skill_to_skills_dir(fake_home):
    """connect() copies skill into ~/.hermes/skills/agentnet/ for discovery."""
    d = fake_home / ".hermes"
    d.mkdir()
    (d / "config.yaml").write_text("model:\n  provider: openai\n")

    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    skill_md = d / "skills" / "agentnet" / "SKILL.md"
    assert skill_md.exists()
    assert "agentnet_discover" in skill_md.read_text()


def test_disconnect_removes_skill_dir(fake_home):
    """disconnect() removes the skill from ~/.hermes/skills/agentnet/."""
    d = fake_home / ".hermes"
    d.mkdir()
    (d / "config.yaml").write_text("plugins:\n  enabled:\n    - agentnet\n")
    skill_dir = d / "skills" / "agentnet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("test")

    HermesConnector().disconnect({})
    assert not skill_dir.exists()
