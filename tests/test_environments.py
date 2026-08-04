"""Tests for infra/environments.py (mocked probes — never invoke cmd.exe/wsl.exe)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agentnet_cli.infra.environments import (
    Environment,
    connection_key,
    detect_environments,
    local_environment,
    parse_connection_key,
    resolve_env_filter,
)


def test_local_environment_defaults(fake_home):
    env = local_environment()
    assert env.kind == "local"
    assert env.key == "local"
    assert env.home == fake_home


def test_detect_environments_no_mirror(fake_home, monkeypatch):
    monkeypatch.setenv("AGENTNET_NO_MIRROR", "1")
    envs = detect_environments()
    assert len(envs) == 1
    assert envs[0].kind == "local"


def test_detect_environments_no_mirror_flag(fake_home, monkeypatch):
    monkeypatch.delenv("AGENTNET_NO_MIRROR", raising=False)
    envs = detect_environments(no_mirror=True)
    assert [e.kind for e in envs] == ["local"]


def test_detect_wsl_adds_windows(fake_home, monkeypatch):
    monkeypatch.delenv("AGENTNET_NO_MIRROR", raising=False)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    # Clear any cached mirror from config
    monkeypatch.setattr(
        "agentnet_cli.infra.environments._load_cached_mirror", lambda: None
    )
    monkeypatch.setattr("agentnet_cli.infra.environments._cache_mirror", lambda env: None)
    monkeypatch.setattr("agentnet_cli.infra.environments._in_wsl", lambda: True)
    monkeypatch.setattr("agentnet_cli.infra.environments._is_native_windows", lambda: False)

    def fake_run_tool(name, args, **kw):
        if name == "cmd.exe":
            return MagicMock(returncode=0, stdout="C:\\Users\\tejas\r\n")
        if name == "wslpath":
            return MagicMock(returncode=0, stdout="/mnt/c/Users/tejas\n")
        return None

    monkeypatch.setattr("agentnet_cli.infra.environments.run_tool", fake_run_tool)

    envs = detect_environments()
    assert len(envs) == 2
    assert envs[0].kind == "local"
    assert envs[1].kind == "windows"
    assert envs[1].home == Path("/mnt/c/Users/tejas")
    assert envs[1].distro == "Ubuntu"


def test_detect_windows_adds_wsl(fake_home, monkeypatch):
    monkeypatch.delenv("AGENTNET_NO_MIRROR", raising=False)
    monkeypatch.setattr(
        "agentnet_cli.infra.environments._load_cached_mirror", lambda: None
    )
    monkeypatch.setattr("agentnet_cli.infra.environments._cache_mirror", lambda env: None)
    monkeypatch.setattr("agentnet_cli.infra.environments._in_wsl", lambda: False)
    monkeypatch.setattr("agentnet_cli.infra.environments._is_native_windows", lambda: True)
    monkeypatch.setattr(
        "agentnet_cli.infra.environments._list_wsl_distros",
        lambda: ["Ubuntu"],
    )

    def fake_run_tool(name, args, **kw):
        if name == "wsl.exe" and "echo $HOME" in " ".join(args):
            return MagicMock(returncode=0, stdout="/home/tejas\n")
        return None

    monkeypatch.setattr("agentnet_cli.infra.environments.run_tool", fake_run_tool)

    envs = detect_environments()
    assert len(envs) == 2
    assert envs[1].kind == "wsl"
    assert envs[1].distro == "Ubuntu"
    assert "Ubuntu" in str(envs[1].home)


def test_connection_key_local_and_mirrored():
    local = Environment(kind="local", label="This machine", home=Path("/home/x"))
    win = Environment(kind="windows", label="Windows", home=Path("/mnt/c/Users/x"), distro="Ubuntu")
    assert connection_key("cursor", local) == "cursor"
    assert connection_key("cursor", win) == "cursor@windows"
    assert parse_connection_key("cursor") == ("cursor", "local")
    assert parse_connection_key("cursor@windows") == ("cursor", "windows")


def test_resolve_env_filter():
    envs = [
        Environment(kind="local", label="This machine", home=Path("/a")),
        Environment(kind="windows", label="Win", home=Path("/b"), distro="Ubuntu"),
    ]
    assert [e.kind for e in resolve_env_filter("local", envs)] == ["local"]
    assert [e.kind for e in resolve_env_filter("windows", envs)] == ["windows"]
    assert resolve_env_filter(None, envs) == envs


def test_hook_command_local(monkeypatch, fake_home):
    monkeypatch.setattr(
        "agentnet_cli.infra.environments.agentnet_invocation",
        lambda: ["/usr/bin/agentnet"],
    )
    env = local_environment()
    cmd = env.hook_command("cursor-hook", "--pre")
    assert "cursor-hook" in cmd and "--pre" in cmd
    assert "agentnet" in cmd


def test_hook_command_windows_bridges_wsl(monkeypatch, fake_home):
    monkeypatch.setattr(
        "agentnet_cli.infra.environments._windows_native_agentnet",
        lambda: None,
    )
    monkeypatch.setattr(
        "agentnet_cli.infra.environments.agentnet_invocation",
        lambda: ["/usr/bin/agentnet"],
    )
    env = Environment(
        kind="windows",
        label="Windows",
        home=Path("/mnt/c/Users/x"),
        distro="Ubuntu",
    )
    cmd = env.hook_command("skill-hook", "--pre")
    assert "wsl.exe" in cmd
    assert "Ubuntu" in cmd
    assert "skill-hook" in cmd


def test_mcp_command_windows_native(monkeypatch, fake_home):
    monkeypatch.setattr(
        "agentnet_cli.infra.environments._windows_native_agentnet",
        lambda: r"C:\Users\x\agentnet.exe",
    )
    env = Environment(
        kind="windows",
        label="Windows",
        home=Path("/mnt/c/Users/x"),
        distro="Ubuntu",
    )
    command, args = env.mcp_command()
    assert command == r"C:\Users\x\agentnet.exe"
    assert args == ["mcp-serve"]
