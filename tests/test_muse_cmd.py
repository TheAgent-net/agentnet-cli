import json

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.config import save_config

runner = CliRunner()
TOKEN = "ank1_abcdefghijklmnopqrstuvwxyz0123"


def test_muse_prints_masked_settings(fake_home, monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    monkeypatch.delenv("AGENTNET_PLATFORM_URL", raising=False)
    monkeypatch.delenv("AGENTNET_URL", raising=False)
    monkeypatch.delenv("AGENTNET_ENV", raising=False)
    save_config({"platform_url": "https://example.test/", "api_token": TOKEN})
    result = runner.invoke(app, ["muse"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["mcp_url"] == "https://example.test/muse/mcp"
    assert data["api_key"] == "ank1_abcd…0123"
    assert TOKEN not in result.stdout
    assert data["policy_url"] == "https://example.test/muse/policy"
    assert "https://example.test/muse/mcp" in data["muse_prompt"]


def test_muse_show_key_prints_full_token(fake_home, monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", TOKEN)
    result = runner.invoke(app, ["muse", "--show-key"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["api_key"] == TOKEN


def test_muse_masks_short_token_entirely(fake_home, monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "short")
    result = runner.invoke(app, ["muse"])
    assert json.loads(result.stdout)["api_key"] == "…"


def test_muse_requires_auth(fake_home, monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    result = runner.invoke(app, ["muse"])
    assert result.exit_code == 1
    assert "Not authenticated" in json.loads(result.stdout)["error"]
