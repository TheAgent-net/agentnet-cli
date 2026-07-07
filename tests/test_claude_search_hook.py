import json

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.connectors import claude_search_hook as h

runner = CliRunner()


def _settings(fake_home):
    return fake_home / ".claude" / "settings.json"


def _cmd(data, event):
    return data["hooks"][event][0]["hooks"][0]["command"]


def test_install_writes_pre_and_post_hooks(fake_home):
    changed, _ = h.install()
    assert changed
    data = json.loads(_settings(fake_home).read_text())
    assert "WebSearch" in data["hooks"]["PreToolUse"][0]["matcher"]
    assert _cmd(data, "PreToolUse") == "agentnet hook-slate --pre"
    assert _cmd(data, "PostToolUse") == "agentnet hook-slate --post"


def test_install_is_idempotent(fake_home):
    assert h.install()[0] is True
    assert h.install()[0] is False  # no duplicates
    data = json.loads(_settings(fake_home).read_text())
    assert len(data["hooks"]["PreToolUse"]) == 1
    assert len(data["hooks"]["PostToolUse"]) == 1


def test_install_preserves_existing_settings(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": "opus", "hooks": {"SessionStart": [{"hooks": []}]}}))
    h.install()
    data = json.loads(p.read_text())
    assert data["model"] == "opus"
    assert "SessionStart" in data["hooks"]
    assert "PreToolUse" in data["hooks"] and "PostToolUse" in data["hooks"]


def test_uninstall_removes_both_agentnet_hooks(fake_home):
    h.install()
    changed, _ = h.uninstall()
    assert changed
    data = json.loads(_settings(fake_home).read_text())
    hooks = data.get("hooks", {})
    assert "PreToolUse" not in hooks and "PostToolUse" not in hooks


def test_uninstall_keeps_user_posttooluse_hooks(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"command": "my-thing"}]}]}
    }))
    h.install()
    h.uninstall()
    data = json.loads(p.read_text())
    posts = data["hooks"]["PostToolUse"]
    assert any(b["hooks"][0]["command"] == "my-thing" for b in posts)
    assert not any("agentnet" in b["hooks"][0]["command"] for b in posts)


def test_cli_enable_and_remove(fake_home):
    r1 = runner.invoke(app, ["enable-search-fire"])
    assert r1.exit_code == 0 and "installed" in r1.stdout
    r2 = runner.invoke(app, ["enable-search-fire", "--remove"])
    assert r2.exit_code == 0 and "removed" in r2.stdout
