"""Hermes plugin entry for Agent-net."""

from __future__ import annotations

from pathlib import Path

from agentnet_cli.tools.tool_defs import TOOL_ACTIONS

from . import handlers, schemas

_PLUGIN_DIR = Path(__file__).resolve().parent

_HANDLER_MAP = {
    "agentnet_search": handlers.agentnet_search,
}


def register(ctx):
    """Register the Agent-net search tool and skill with Hermes."""
    for schema in schemas.SCHEMAS:
        name = schema["name"]
        if name not in _HANDLER_MAP:
            continue
        ctx.register_tool(
            name=name,
            toolset="agentnet",
            schema=schema,
            handler=_HANDLER_MAP[name],
        )

    skills_dir = _PLUGIN_DIR / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)


__all__ = ["TOOL_ACTIONS", "register"]
