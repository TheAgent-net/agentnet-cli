from __future__ import annotations

from pathlib import Path


def bundled_integrations_root() -> Path:
    """Root of Claude/OpenClaw plugin trees shipped inside the installed package."""
    return Path(__file__).resolve().parent.parent / "integrations"


def bundled_claude_marketplace() -> Path:
    return bundled_integrations_root() / "claude"


def bundled_openclaw_plugin() -> Path:
    return bundled_integrations_root() / "openclaw"


def bundled_discovery_base() -> Path:
    return bundled_integrations_root() / "shared" / "discovery-skill.base.md"
