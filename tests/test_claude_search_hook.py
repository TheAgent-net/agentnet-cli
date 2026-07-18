import json

import pytest
from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.connectors import claude_search_hook as h
from agentnet_cli.connectors.claude_search_hook import SettingsHookError

runner = CliRunner()


def _settings(fake_home):
    return fake_home / ".claude" / "settings.json"


def _cmd(data, event):
    return data["hooks"][event][0]["hooks"][0]["command"]


def test_install_writes_all_three_hooks(fake_home):
    changed, _ = h.install()
    assert changed
    data = json.loads(_settings(fake_home).read_text())
    assert _cmd(data, "UserPromptSubmit") == "agentnet skill-hook --pre"
    assert _cmd(data, "PostToolUse") == "agentnet skill-hook --peek"
    assert _cmd(data, "Stop") == "agentnet skill-hook --post"
    # UserPromptSubmit/Stop are not tool-scoped -> no matcher; PostToolUse is -> "*"
    assert "matcher" not in data["hooks"]["UserPromptSubmit"][0]
    assert "matcher" not in data["hooks"]["Stop"][0]
    assert data["hooks"]["PostToolUse"][0]["matcher"] == "*"


def test_install_is_idempotent(fake_home):
    assert h.install()[0] is True
    assert h.install()[0] is False  # no duplicates
    data = json.loads(_settings(fake_home).read_text())
    assert len(data["hooks"]["UserPromptSubmit"]) == 1
    assert len(data["hooks"]["PostToolUse"]) == 1
    assert len(data["hooks"]["Stop"]) == 1


def test_install_preserves_existing_settings(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": "opus", "hooks": {"SessionStart": [{"hooks": []}]}}))
    h.install()
    data = json.loads(p.read_text())
    assert data["model"] == "opus"
    assert "SessionStart" in data["hooks"]
    assert "UserPromptSubmit" in data["hooks"] and "Stop" in data["hooks"]


def test_uninstall_removes_both_agentnet_hooks(fake_home):
    h.install()
    changed, _ = h.uninstall()
    assert changed
    data = json.loads(_settings(fake_home).read_text())
    hooks = data.get("hooks", {})
    assert "UserPromptSubmit" not in hooks and "PostToolUse" not in hooks and "Stop" not in hooks


def test_uninstall_keeps_user_stop_hooks(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "hooks": {"Stop": [{"hooks": [{"command": "my-thing"}]}]}
    }))
    h.install()
    h.uninstall()
    data = json.loads(p.read_text())
    stops = data["hooks"]["Stop"]
    assert any(b["hooks"][0]["command"] == "my-thing" for b in stops)
    assert not any("agentnet" in b["hooks"][0]["command"] for b in stops)


def test_cli_enable_and_remove(fake_home):
    r1 = runner.invoke(app, ["enable-skill-fire"])
    assert r1.exit_code == 0 and "installed" in r1.stdout
    r2 = runner.invoke(app, ["enable-skill-fire", "--remove"])
    assert r2.exit_code == 0 and "removed" in r2.stdout


# ── Fix A: malformed settings.json must never be overwritten ──────────────────
def test_install_raises_on_malformed_json_and_leaves_file_untouched(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    original = '{"model": "opus", "hooks": {  '  # truncated -> invalid JSON
    p.write_text(original)
    with pytest.raises(SettingsHookError):
        h.install()
    assert p.read_text() == original  # byte-for-byte untouched


def test_install_raises_on_non_object_settings(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[]")  # valid JSON, but not an object
    with pytest.raises(SettingsHookError):
        h.install()
    assert p.read_text() == "[]"


def test_uninstall_noops_on_malformed_settings(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ broken")
    changed, _ = h.uninstall()  # must not raise or touch the file
    assert changed is False
    assert p.read_text() == "{ broken"


def test_cli_enable_fails_on_malformed_settings(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json")
    r = runner.invoke(app, ["enable-skill-fire"])
    assert r.exit_code != 0 and "JSON" in r.stdout
    assert p.read_text() == "{ not json"  # preserved


# ── Fix B: a non-list event value must be preserved, not replaced with [] ──────
def test_install_preserves_event_stored_as_object(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"PostToolUse": {"hooks": [{"command": "user-thing"}]}}}))
    h.install()
    post = json.loads(p.read_text())["hooks"]["PostToolUse"]
    assert isinstance(post, list)
    cmds = [b.get("hooks", [{}])[0].get("command") for b in post]
    assert "user-thing" in cmds  # the user's object block was wrapped + kept
    assert "agentnet skill-hook --peek" in cmds  # ours appended


def test_install_skips_event_with_scalar_value(fake_home):
    p = _settings(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"Stop": "weird"}}))
    h.install()
    data = json.loads(p.read_text())
    assert data["hooks"]["Stop"] == "weird"  # scalar left untouched
    assert _cmd(data, "UserPromptSubmit") == "agentnet skill-hook --pre"  # others still installed
