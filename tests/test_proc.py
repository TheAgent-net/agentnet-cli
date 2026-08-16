"""Tests for infra/proc.py cross-platform helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

from agentnet_cli.infra import proc


def test_find_executable_found(monkeypatch):
    monkeypatch.setattr(proc.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert proc.find_executable("claude") == "/usr/bin/claude"


def test_find_executable_missing(monkeypatch):
    monkeypatch.setattr(proc.shutil, "which", lambda name: None)
    assert proc.find_executable("nope") is None


def test_run_tool_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(proc, "find_executable", lambda name: None)
    assert proc.run_tool("missing", ["--help"]) is None


def test_run_tool_resolves_and_runs(monkeypatch):
    monkeypatch.setattr(proc, "find_executable", lambda name: "/opt/bin/uv")
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="ok"))
    monkeypatch.setattr(proc.subprocess, "run", mock_run)
    result = proc.run_tool("uv", ["tool", "list"], text=True, timeout=5)
    assert result is not None
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == ["/opt/bin/uv", "tool", "list"]


def test_run_tool_timeout_returns_none(monkeypatch):
    monkeypatch.setattr(proc, "find_executable", lambda name: "/usr/bin/wsl.exe")

    def _raise(*_a, **_k):
        raise proc.subprocess.TimeoutExpired(cmd="wsl.exe", timeout=1)

    monkeypatch.setattr(proc.subprocess, "run", _raise)
    assert proc.run_tool("wsl.exe", ["-l", "-q"], timeout=1) is None


def test_agentnet_invocation_prefers_which(monkeypatch):
    monkeypatch.setattr(proc, "find_executable", lambda name: "/usr/local/bin/agentnet")
    inv = proc.agentnet_invocation()
    assert inv == [os.path.abspath("/usr/local/bin/agentnet")]


def test_agentnet_invocation_module_fallback(monkeypatch):
    monkeypatch.setattr(proc, "find_executable", lambda name: None)
    inv = proc.agentnet_invocation()
    assert inv == [sys.executable, "-m", "agentnet_cli"]


def test_is_agentnet_subcommand_variants():
    assert proc.is_agentnet_subcommand("agentnet skill-hook --pre", "skill-hook")
    assert proc.is_agentnet_subcommand("/usr/bin/agentnet skill-hook --peek", "skill-hook")
    assert proc.is_agentnet_subcommand(
        r"C:\Users\x\agentnet.exe skill-hook --pre", "skill-hook"
    )
    assert proc.is_agentnet_subcommand(
        "wsl.exe -d Ubuntu -- /usr/bin/agentnet skill-hook --pre", "skill-hook"
    )
    assert not proc.is_agentnet_subcommand("agentnet cursor-hook --pre", "skill-hook")
    assert not proc.is_agentnet_subcommand(
        '/opt/wrapper.sh --run "agentnet skill-hook --pre"', "skill-hook"
    )
    assert not proc.is_agentnet_subcommand(None, "skill-hook")


def test_local_hook_command_quotes(monkeypatch):
    monkeypatch.setattr(proc, "agentnet_invocation", lambda: ["/opt/my tools/agentnet"])
    cmd = proc.local_hook_command("skill-hook", "--pre")
    assert "skill-hook" in cmd and "--pre" in cmd
    if os.name != "nt":
        assert "'/opt/my tools/agentnet'" in cmd or "/opt/my tools/agentnet" in cmd


def test_start_detached_process_posix(monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX creationflags path")
    mock_popen = MagicMock()
    monkeypatch.setattr(proc.subprocess, "Popen", mock_popen)
    proc.start_detached_process(["agentnet", "skill-hook", "--fetch"])
    kwargs = mock_popen.call_args.kwargs
    assert kwargs.get("start_new_session") is True


def test_start_detached_process_windows(monkeypatch):
    # Force Windows branch without replacing the os module (breaks pathlib).
    monkeypatch.setattr(proc.os, "name", "nt")
    mock_popen = MagicMock()
    monkeypatch.setattr(proc.subprocess, "Popen", mock_popen)
    proc.start_detached_process(["agentnet.exe", "update"])
    kwargs = mock_popen.call_args.kwargs
    assert "creationflags" in kwargs
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200 | 0x08000000
