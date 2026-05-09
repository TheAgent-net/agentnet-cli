from pathlib import Path
from unittest.mock import patch
from agentnet_cli.detect import detect_all
from agentnet_cli.paths import AgentName


def _make_agent_dir(home: Path, dot_dir: str, files: list[str]) -> None:
    d = home / dot_dir
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        p = d / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")


def test_detects_claude_by_settings(fake_home):
    _make_agent_dir(fake_home, ".claude", ["settings.json"])
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CLAUDE].detected is True


def test_detects_cursor_by_extensions_dir(fake_home):
    (fake_home / ".cursor" / "extensions").mkdir(parents=True)
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CURSOR].detected is True


def test_not_detected_when_dir_missing(fake_home):
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CLAUDE].detected is False
    assert by_name[AgentName.CURSOR].detected is False


def test_detects_codex_by_config_toml(fake_home):
    _make_agent_dir(fake_home, ".codex", ["config.toml"])
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CODEX].detected is True


def test_detects_hermes_by_config_yaml(fake_home):
    _make_agent_dir(fake_home, ".hermes", ["config.yaml"])
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.HERMES].detected is True


def test_detects_openclaw_by_openclaw_json(fake_home):
    _make_agent_dir(fake_home, ".openclaw", ["openclaw.json"])
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.OPENCLAW].detected is True


def test_detects_copilot_by_config_json(fake_home):
    _make_agent_dir(fake_home, ".copilot", ["config.json"])
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.COPILOT].detected is True


def test_detects_vscode_by_extensions_dir(fake_home):
    (fake_home / ".vscode" / "extensions").mkdir(parents=True)
    results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.VSCODE].detected is True


def test_binary_found_when_on_path(fake_home):
    _make_agent_dir(fake_home, ".claude", ["settings.json"])
    with patch("agentnet_cli.paths.shutil.which", lambda name: "/usr/local/bin/claude" if name == "claude" else None):
        results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CLAUDE].binary_found is True
    assert str(by_name[AgentName.CLAUDE].binary_path) == "/usr/local/bin/claude"


def test_binary_not_found(fake_home):
    _make_agent_dir(fake_home, ".claude", ["settings.json"])
    with patch("agentnet_cli.paths.shutil.which", return_value=None):
        results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CLAUDE].detected is True
    assert by_name[AgentName.CLAUDE].binary_found is False
    assert by_name[AgentName.CLAUDE].binary_path is None


def test_custom_path_takes_precedence(fake_home):
    _make_agent_dir(fake_home, ".claude", ["settings.json"])
    custom_bin = fake_home / "custom-claude"
    custom_bin.write_text("#!/bin/sh\n")
    custom_bin.chmod(0o755)
    from agentnet_cli.config import save_agent_path
    save_agent_path("claude", str(custom_bin))
    with patch("agentnet_cli.paths.shutil.which", return_value=None):
        results = detect_all()
    by_name = {r.agent_name: r for r in results}
    assert by_name[AgentName.CLAUDE].binary_found is True
    assert by_name[AgentName.CLAUDE].binary_path == custom_bin
