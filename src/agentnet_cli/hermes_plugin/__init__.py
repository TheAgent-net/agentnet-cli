from __future__ import annotations

from pathlib import Path

from . import handlers, schemas

_PLUGIN_DIR = Path(__file__).resolve().parent

_HANDLER_MAP = {
    "agentnet_discover": handlers.agentnet_discover,
    "agentnet_discover_agents": handlers.agentnet_discover_agents,
    "agentnet_get_agent": handlers.agentnet_get_agent,
    "agentnet_use_agent": handlers.agentnet_use_agent,
    "agentnet_continue_session": handlers.agentnet_continue_session,
    "agentnet_settle_session": handlers.agentnet_settle_session,
    "agentnet_wallet": handlers.agentnet_wallet,
    "agentnet_wallet_topup": handlers.agentnet_wallet_topup,
}


def register(ctx):
    for schema in schemas.SCHEMAS:
        name = schema["name"]
        ctx.register_tool(
            name=name,
            toolset="agentnet",
            schema=schema,
            handler=_HANDLER_MAP[name],
        )

    skills_dir = _PLUGIN_DIR / "skills"
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)
