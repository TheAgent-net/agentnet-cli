from __future__ import annotations

from pathlib import Path


def bundled_integrations_root() -> Path:
    """Root of Claude/OpenClaw plugin trees shipped inside the installed package."""
    return Path(__file__).resolve().parent.parent / "integrations"


def bundled_claude_marketplace() -> Path:
    return bundled_integrations_root() / "claude"


def bundled_openclaw_plugin() -> Path:
    return bundled_integrations_root() / "openclaw"


def bundled_opencode_plugin() -> Path:
    """Directory holding the opencode JS plugin (agentnet.js) shipped in the wheel."""
    return bundled_integrations_root() / "opencode"


def bundled_discovery_base() -> Path:
    return bundled_integrations_root() / "shared" / "discovery-skill.base.md"
