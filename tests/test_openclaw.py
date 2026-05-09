import json
from pathlib import Path
from agentnet_cli.agents.openclaw import OpenClawConnector


def _setup_openclaw(home: Path) -> None:
    d = home / ".openclaw"
    d.mkdir()
    (d / "openclaw.json").write_text("{}")


def test_detect(fake_home):
    _setup_openclaw(fake_home)
    assert OpenClawConnector().detect().detected is True


def test_connect_adds_plugin(fake_home):
    _setup_openclaw(fake_home)
    result = OpenClawConnector().connect({"api_token": "agn_t", "platform_url": "https://x"})
    assert result.success
    data = json.loads((fake_home / ".openclaw" / "openclaw.json").read_text())
    assert "agentnet-gateway" in data.get("plugins", {})


def test_connect_sets_permissions(fake_home):
    """openclaw.json gets 0600 permissions after connect (C-2 fix)."""
    import os
    import stat

    _setup_openclaw(fake_home)
    OpenClawConnector().connect({"api_token": "agn_t", "platform_url": "https://x"})
    config_path = fake_home / ".openclaw" / "openclaw.json"
    if os.name != "nt":
        mode = config_path.stat().st_mode
        assert mode & stat.S_IRUSR
        assert mode & stat.S_IWUSR
        assert not (mode & stat.S_IRGRP)
        assert not (mode & stat.S_IROTH)
