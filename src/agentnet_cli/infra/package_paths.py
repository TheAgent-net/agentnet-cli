"""Paths to bundled integration assets in the installed package."""

from __future__ import annotations

from pathlib import Path


def bundled_integrations_root() -> Path:
    """Return the root of Claude, Cursor, Hermes, and OpenClaw plugin trees."""
    return Path(__file__).resolve().parent.parent / "integrations"


def bundled_claude_marketplace() -> Path:
    """Return the path to the bundled Claude marketplace tree."""
    return bundled_integrations_root() / "claude"


def bundled_cursor_marketplace() -> Path:
    """Return the path to the bundled Cursor marketplace tree."""
    return bundled_integrations_root() / "cursor"


def bundled_cursor_plugin() -> Path:
    """Return the path to the bundled Cursor plugin tree."""
    return bundled_cursor_marketplace() / "plugin"


def bundled_hermes_plugin() -> Path:
    """Return the path to the bundled Hermes plugin tree."""
    return bundled_integrations_root() / "hermes"


def bundled_openclaw_plugin() -> Path:
    """Return the path to the bundled OpenClaw plugin tree."""
    return bundled_integrations_root() / "openclaw"


def bundled_discovery_base() -> Path:
    """Return the path to the shared discovery skill template."""
    return bundled_integrations_root() / "shared" / "discovery-skill.base.md"
