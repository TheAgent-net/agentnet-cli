import os
import stat
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


def test_connect_merges_yaml(fake_home):
    _setup_hermes(fake_home)
    result = HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    assert "agentnet" in data.get("mcp_servers", {})


def test_disconnect(fake_home):
    """Connect then disconnect — MCP server and skill removed from config."""
    _setup_hermes(fake_home)
    config_path = fake_home / ".hermes" / "config.yaml"
    connector = HermesConnector()
    result = connector.connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success

    # Build a manifest entry like record_connection would
    manifest_entry = {
        "mcp_registered": result.mcp_entry,
        "files_created": [str(p) for p in result.files_created],
    }

    ok = connector.disconnect(manifest_entry)
    assert ok

    data = yaml.safe_load(config_path.read_text()) or {}
    assert "agentnet" not in data.get("mcp_servers", {})

    skill_dir = fake_home / ".hermes" / "skills" / "agentnet"
    assert not skill_dir.exists()


def test_connect_sets_file_permissions(fake_home):
    """config.yaml gets 0600 permissions after connect (C-2 fix)."""
    _setup_hermes(fake_home)
    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    config_path = fake_home / ".hermes" / "config.yaml"
    if os.name != "nt":
        mode = config_path.stat().st_mode
        assert mode & stat.S_IRUSR
        assert mode & stat.S_IWUSR
        assert not (mode & stat.S_IRGRP)
        assert not (mode & stat.S_IROTH)


def test_connect_sort_keys_false(fake_home):
    """YAML output preserves insertion order (sort_keys=False)."""
    _setup_hermes(fake_home)
    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    config_path = fake_home / ".hermes" / "config.yaml"
    text = config_path.read_text()
    # "model" key was written first in the original; it should appear before mcp_servers
    model_pos = text.find("model:")
    mcp_pos = text.find("mcp_servers:")
    assert model_pos < mcp_pos, "Keys should not be alphabetically sorted"
