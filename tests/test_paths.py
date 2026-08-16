from pathlib import Path
from agentnet_cli.infra.paths import agent_binary_name, agent_config_root, agentnet_home, find_agent_binary, AgentName


def test_agentnet_home_returns_dot_agentnet(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agentnet_home() == tmp_path / ".agentnet"


def test_claude_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    # Host APPDATA (common on Windows CI) must not override a patched home.
    monkeypatch.setenv("APPDATA", str(Path.cwd() / "unrelated-AppData"))
    assert agent_config_root(AgentName.CLAUDE) == tmp_path / ".claude"


def test_claude_config_root_uses_appdata_when_under_home(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    monkeypatch.setattr("agentnet_cli.infra.paths.sys.platform", "win32")
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    assert agent_config_root(AgentName.CLAUDE) == appdata / "Claude"


def test_claude_config_root_mirrored_windows(tmp_path):
    from agentnet_cli.infra.environments import Environment

    win_home = tmp_path / "Users" / "testuser"
    (win_home / "AppData" / "Roaming").mkdir(parents=True)
    env = Environment(kind="windows", label="Windows", home=win_home, distro="Ubuntu")
    assert agent_config_root(AgentName.CLAUDE, env) == win_home / "AppData" / "Roaming" / "Claude"


def test_cursor_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agent_config_root(AgentName.CURSOR) == tmp_path / ".cursor"


def test_copilot_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agent_config_root(AgentName.COPILOT) == tmp_path / ".copilot"


def test_codex_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agent_config_root(AgentName.CODEX) == tmp_path / ".codex"


def test_hermes_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agent_config_root(AgentName.HERMES) == tmp_path / ".hermes"


def test_openclaw_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agent_config_root(AgentName.OPENCLAW) == tmp_path / ".openclaw"


def test_vscode_config_root(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    assert agent_config_root(AgentName.VSCODE) == tmp_path / ".vscode"


def test_agent_binary_name():
    assert agent_binary_name(AgentName.CLAUDE) == "claude"
    assert agent_binary_name(AgentName.COPILOT) == "copilot"
    assert agent_binary_name(AgentName.VSCODE) == "code"


def test_find_agent_binary_custom_path(tmp_path):
    fake_bin = tmp_path / "my-claude"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    result = find_agent_binary(AgentName.CLAUDE, {"claude": str(fake_bin)})
    assert result == fake_bin


def test_find_agent_binary_custom_path_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.shutil.which", lambda _: None)
    result = find_agent_binary(AgentName.CLAUDE, {"claude": str(tmp_path / "missing")})
    assert result is None


def test_find_agent_binary_falls_back_to_which(monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.shutil.which", lambda name: f"/usr/bin/{name}" if name == "claude" else None)
    result = find_agent_binary(AgentName.CLAUDE)
    assert result == Path("/usr/bin/claude")
