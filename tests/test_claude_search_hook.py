import json

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.connectors import claude_search_hook as h

runner = CliRunner()


def _settings(fake_home):
    return fake_home / ".claude" / "settings.json"


def test_install_writes_posttooluse_hook(fake_home):
    changed, _ = h.install()
    assert changed
    data = json.loads(_settings(fake_home).read_text())
    block = data["hooks"]["PostToolUse"][0]
    assert "WebSearch" in block["matcher"]
    assert block["hooks"][0]["command"] == "agentnet hook-slate"


def test_install_is_idempotent(fake_home):
    assert h.install()[0] is True
    assert h.install()[0] is False  # already present, no duplicate
    data = json.loads(_settings(fake_home).read_text())
    assert len(data["hooks"]["PostToolUse"]) == 1


def test_install_preserves_existing_settings(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": "opus", "hooks": {"SessionStart": [{"hooks": []}]}}))
    h.install()
    data = json.loads(p.read_text())
    assert data["model"] == "opus"
    assert "SessionStart" in data["hooks"]
    assert "PostToolUse" in data["hooks"]


def test_uninstall_removes_only_agentnet_hook(fake_home):
    h.install()
    changed, _ = h.uninstall()
    assert changed
    data = json.loads(_settings(fake_home).read_text())
    assert "PostToolUse" not in data.get("hooks", {})


def test_cli_enable_and_remove(fake_home):
    r1 = runner.invoke(app, ["enable-search-fire"])
    assert r1.exit_code == 0 and "installed" in r1.stdout
    r2 = runner.invoke(app, ["enable-search-fire", "--remove"])
    assert r2.exit_code == 0 and "removed" in r2.stdout
