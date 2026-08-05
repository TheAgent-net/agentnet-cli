"""Install the AgentNet skill-fire plugin into opencode's ``~/.config/opencode/plugins/``.

opencode auto-loads any ``.js``/``.ts`` file in that directory at startup (the ``plugin`` config
array only accepts npm package names, not local paths — confirmed against opencode's docs), so we
simply copy the bundled ``agentnet.js`` there. The ``__AGENTNET_BIN__`` placeholder is resolved to
the ``agentnet`` CLI's absolute path on the way in, so the plugin doesn't depend on opencode's PATH.
Install is idempotent (only rewrites when the resolved content changes).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..infra.package_paths import bundled_opencode_plugin
from ..infra.paths import AgentName, agent_config_root

_PLUGIN_FILENAME = "agentnet.js"
_BIN_PLACEHOLDER = "__AGENTNET_BIN__"


def plugins_dir() -> Path:
    return agent_config_root(AgentName.OPENCODE) / "plugins"


def plugin_path() -> Path:
    return plugins_dir() / _PLUGIN_FILENAME


def _resolve_agentnet_bin() -> str:
    return shutil.which("agentnet") or "agentnet"


def _rendered_plugin() -> str:
    src = bundled_opencode_plugin() / _PLUGIN_FILENAME
    if not src.is_file():
        raise FileNotFoundError(
            f"Bundled opencode plugin missing at {src}. "
            "Reinstall agentnet-cli: pip install --upgrade agentnet-cli"
        )
    return src.read_text().replace(_BIN_PLACEHOLDER, _resolve_agentnet_bin())


def install() -> tuple[bool, Path]:
    """Write the plugin (with the CLI path resolved) into the opencode plugins dir.

    Returns ``(changed, path)``.
    """
    dest = plugin_path()
    content = _rendered_plugin()
    if dest.exists() and dest.read_text() == content:
        return False, dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    return True, dest


def uninstall() -> tuple[bool, Path]:
    """Remove the plugin file (and the plugins dir if we emptied it). Returns ``(changed, path)``."""
    dest = plugin_path()
    if not dest.exists():
        return False, dest
    dest.unlink()
    parent = dest.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
    return True, dest
