"""Environment abstraction for local, Windows, and WSL interop."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .proc import (
    agentnet_invocation,
    find_executable,
    format_cmdline,
    run_tool,
)


@dataclass(frozen=True)
class Environment:
    """A target home directory where agent configs may live."""

    kind: str  # "local" | "windows" | "wsl"
    label: str
    home: Path
    distro: str | None = None

    @property
    def key(self) -> str:
        """Return a stable key for manifest and ``--env`` scoping."""
        if self.kind == "local":
            return "local"
        if self.kind == "wsl" and self.distro:
            return f"wsl:{self.distro}"
        return self.kind

    def hook_command(self, subcmd: str, *flags: str) -> str:
        """Return the command string agents in this environment should run."""
        argv = self._invocation_argv(subcmd, *flags)
        return format_cmdline(argv)

    def mcp_command(self) -> tuple[str, list[str]]:
        """Return ``(command, args)`` for an MCP server entry in this environment."""
        argv = self._invocation_argv("mcp-serve")
        return argv[0], argv[1:]

    def to_env_path(self, p: Path) -> str:
        """Return *p* as a path string seen from this environment."""
        s = str(p)
        if self.kind == "local":
            return s
        if self.kind == "windows":
            # Writing Windows-side configs from WSL: need a Windows path.
            if sys.platform != "win32":
                converted = _wslpath_w(s)
                if converted:
                    return converted
            return s
        if self.kind == "wsl":
            # Writing WSL-side configs from Windows: prefer /mnt/... form.
            if os.name == "nt":
                converted = _wslpath_u(s, distro=self.distro)
                if converted:
                    return converted
            return s
        return s

    def _invocation_argv(self, *tail: str) -> list[str]:
        """Build argv to run agentnet in this environment."""
        if self.kind == "local":
            return [*agentnet_invocation(), *tail]

        if self.kind == "windows":
            native = _windows_native_agentnet()
            if native:
                return [native, *tail]
            distro = self.distro or _current_wsl_distro() or "Ubuntu"
            local = agentnet_invocation()
            return ["wsl.exe", "-d", distro, "--", *local, *tail]

        if self.kind == "wsl":
            distro = self.distro or "Ubuntu"
            wsl_bin = _wsl_which_agentnet(distro)
            if wsl_bin:
                return [wsl_bin, *tail]
            # Fall back to the Windows exe; WSL binfmt runs .exe directly.
            local = agentnet_invocation()
            translated = [_windows_path_for_wsl(x) for x in local]
            return [*translated, *tail]

        return [*agentnet_invocation(), *tail]


def local_environment() -> Environment:
    """Return the local machine environment."""
    return Environment(kind="local", label="This machine", home=Path.home())


def mirroring_disabled(*, no_mirror: bool = False) -> bool:
    """Return True when cross-environment mirroring is off."""
    if no_mirror:
        return True
    return os.environ.get("AGENTNET_NO_MIRROR", "").strip() in {"1", "true", "yes"}


def detect_environments(*, no_mirror: bool = False) -> list[Environment]:
    """Return environments to configure. Always put local first."""
    envs = [local_environment()]
    if mirroring_disabled(no_mirror=no_mirror):
        return envs

    cached = _load_cached_mirror()
    if cached is not None:
        envs.append(cached)
        return envs

    if _in_wsl():
        win = _probe_windows_from_wsl()
        if win is not None:
            _cache_mirror(win)
            envs.append(win)
    elif _is_native_windows():
        wsl = _probe_wsl_from_windows()
        if wsl is not None:
            _cache_mirror(wsl)
            envs.append(wsl)

    return envs


def resolve_env_filter(spec: str | None, envs: list[Environment]) -> list[Environment]:
    """Filter *envs* by an ``--env`` value (``local``, ``windows``, or ``wsl[:distro]``)."""
    if not spec:
        return envs
    spec = spec.strip().lower()
    if spec == "local":
        return [e for e in envs if e.kind == "local"]
    if spec == "windows":
        return [e for e in envs if e.kind == "windows"]
    if spec == "wsl" or spec.startswith("wsl:"):
        distro = spec.split(":", 1)[1] if ":" in spec else None
        out = [e for e in envs if e.kind == "wsl"]
        if distro:
            out = [e for e in out if (e.distro or "").lower() == distro.lower()]
        return out
    # Exact key match
    return [e for e in envs if e.key.lower() == spec]


def connection_key(agent: str, env: Environment) -> str:
    """Return the manifest connection key: bare agent for local, ``agent@env`` otherwise."""
    if env.kind == "local":
        return agent
    return f"{agent}@{env.key}"


def parse_connection_key(key: str) -> tuple[str, str]:
    """Split a manifest key into ``(agent, env_key)``."""
    if "@" in key:
        agent, env_key = key.split("@", 1)
        return agent, env_key
    return key, "local"


# ── detection helpers ────────────────────────────────────────────────────────


def _in_wsl() -> bool:
    """Return True when the process runs inside WSL."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in version


def _is_native_windows() -> bool:
    """Return True on native Windows. Use this in tests instead of patching ``os.name``."""
    return os.name == "nt"


def _current_wsl_distro() -> str | None:
    """Return the current WSL distro name, or ``None``."""
    return os.environ.get("WSL_DISTRO_NAME") or None


def _probe_windows_from_wsl() -> Environment | None:
    """Probe for a Windows home directory from inside WSL."""
    proc = run_tool("cmd.exe", ["/c", "echo %USERPROFILE%"], timeout=15, text=True)
    if proc is None or proc.returncode != 0:
        return None
    win_home = (proc.stdout or "").strip().strip("\r")
    if not win_home or "%" in win_home:
        return None
    unix = _wslpath_u(win_home)
    if not unix:
        return None
    home = Path(unix)
    distro = _current_wsl_distro()
    return Environment(
        kind="windows",
        label=f"Windows ({win_home})",
        home=home,
        distro=distro,
    )


def _probe_wsl_from_windows() -> Environment | None:
    """Probe for a WSL home directory from native Windows."""
    distros = _list_wsl_distros()
    if not distros:
        return None
    distro = distros[0]
    proc = run_tool(
        "wsl.exe",
        ["-d", distro, "--", "sh", "-lc", "echo $HOME"],
        timeout=20,
        text=True,
    )
    if proc is None or proc.returncode != 0:
        return None
    linux_home = (proc.stdout or "").strip().splitlines()
    if not linux_home:
        return None
    home_str = linux_home[-1].strip()
    if not home_str.startswith("/"):
        return None
    # UNC path into the distro filesystem
    unc = Path(f"\\\\wsl$\\{distro}{home_str}")
    return Environment(
        kind="wsl",
        label=f"WSL ({distro})",
        home=unc,
        distro=distro,
    )


def _list_wsl_distros() -> list[str]:
    """Return WSL distro names with the default first.

    Output of ``wsl -l -q`` is UTF-16-LE on Windows.
    """
    resolved = find_executable("wsl.exe") or find_executable("wsl")
    if not resolved:
        return []
    try:
        proc = subprocess.run(  # noqa: S603
            [resolved, "-l", "-q"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    raw = proc.stdout or b""
    # ``wsl -l -q`` emits UTF-16-LE on Windows; fall back to utf-8.
    if raw[:2] == b"\xff\xfe" or (len(raw) >= 4 and raw[1:2] == b"\x00"):
        text = raw.decode("utf-16-le", errors="ignore")
    else:
        text = raw.decode("utf-8", errors="ignore")
    names = [ln.strip("\x00").strip() for ln in text.splitlines() if ln.strip("\x00").strip()]
    return [n for n in names if n and not n.startswith("(")]

def _wslpath_u(win_path: str, *, distro: str | None = None) -> str | None:
    """Convert a Windows path to a Unix path."""
    args = ["-u", win_path]
    if distro and os.name == "nt":
        proc = run_tool("wsl.exe", ["-d", distro, "--", "wslpath", *args], timeout=10, text=True)
    else:
        proc = run_tool("wslpath", args, timeout=10, text=True)
    if proc is None or proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def _wslpath_w(unix_path: str) -> str | None:
    """Convert a Unix path to a Windows path."""
    proc = run_tool("wslpath", ["-w", unix_path], timeout=10, text=True)
    if proc is None or proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def _windows_native_agentnet() -> str | None:
    """Return the Windows PATH entry for agentnet when interop shows it."""
    proc = run_tool("where.exe", ["agentnet"], timeout=10, text=True)
    if proc is None or proc.returncode != 0:
        return None
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return lines[0] if lines else None


def _wsl_which_agentnet(distro: str) -> str | None:
    """Return the agentnet binary path inside a WSL distro."""
    proc = run_tool(
        "wsl.exe",
        ["-d", distro, "--", "which", "agentnet"],
        timeout=15,
        text=True,
    )
    if proc is None or proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip().splitlines()
    return out[0].strip() if out else None


def _windows_path_for_wsl(path: str) -> str:
    """Convert a Windows path to a WSL ``/mnt/...`` path when possible."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return path


# ── cache in ~/.agentnet/config.json ─────────────────────────────────────────


def _load_cached_mirror() -> Environment | None:
    """Load a cached mirror environment from config."""
    try:
        from .config import load_config  # noqa: PLC0415

        config = load_config() or {}
        raw = config.get("mirror_environment")
        if not isinstance(raw, dict):
            return None
        kind = raw.get("kind")
        home = raw.get("home")
        label = raw.get("label")
        if not kind or not home or not label:
            return None
        return Environment(
            kind=str(kind),
            label=str(label),
            home=Path(str(home)),
            distro=raw.get("distro"),
        )
    except Exception:  # noqa: BLE001
        return None


def _cache_mirror(env: Environment) -> None:
    """Save a mirror environment to config."""
    try:
        from .config import load_config, save_config  # noqa: PLC0415

        config = load_config() or {}
        config["mirror_environment"] = {
            "kind": env.kind,
            "label": env.label,
            "home": str(env.home),
            "distro": env.distro,
        }
        save_config(config)
    except Exception:  # noqa: BLE001
        pass
