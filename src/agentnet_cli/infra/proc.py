"""Cross-platform subprocess helpers for agentnet-cli."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Any


class ToolNotFoundError(FileNotFoundError):
    """Raised when a tool name is not on PATH."""


def find_executable(name: str) -> str | None:
    """Find *name* on PATH (PATHEXT-aware on Windows)."""
    return shutil.which(name)


def format_cmdline(argv: list[str]) -> str:
    """Quote *argv* for a shell or config command string."""
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def agentnet_invocation() -> list[str]:
    """Return argv to run the agentnet CLI again."""
    found = find_executable("agentnet")
    if found:
        return [os.path.abspath(found)]
    return [sys.executable, "-m", "agentnet_cli"]


def local_hook_command(subcmd: str, *flags: str) -> str:
    """Build a quoted local hook command with an absolute agentnet path."""
    return format_cmdline([*agentnet_invocation(), subcmd, *flags])


def agentnet_basename(token: str) -> str:
    """Return the basename of an executable token, without ``.exe`` or path separators."""
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def is_agentnet_subcommand(cmd: Any, subcmd: str) -> bool:
    """Return True if *cmd* runs agentnet with the given subcommand.

    Match bare names, absolute paths, ``.exe`` suffixes, and
    ``wsl.exe … -- agentnet …`` forms. Use basename minus ``.exe``.
    """
    if not isinstance(cmd, str):
        return False
    parts = cmd.split()
    for i, part in enumerate(parts):
        if agentnet_basename(part) == "agentnet":
            return i + 1 < len(parts) and parts[i + 1] == subcmd
    return False


def run_tool(
    name: str,
    args: list[str],
    *,
    timeout: float | None = None,
    capture: bool = True,
    text: bool = False,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any] | None:
    """Find *name* on PATH, then run it with *args*.

    Return ``None`` when the executable is not found. Do not raise
    ``FileNotFoundError`` from subprocess.
    """
    path = find_executable(name)
    if not path:
        return None
    run_kwargs: dict[str, Any] = {"timeout": timeout, "check": check, **kwargs}
    if capture:
        run_kwargs.setdefault("capture_output", True)
    if text:
        run_kwargs["text"] = True
    try:
        return subprocess.run([path, *args], **run_kwargs)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        # Missing/broken interop tools (e.g. nested wsl.exe from WSL) must not
        # crash detect/connect — treat as "tool unavailable".
        return None


def start_detached_process(argv: list[str]) -> None:
    """Start *argv* as a background process. Do not wait."""
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, **kwargs)  # noqa: S603
